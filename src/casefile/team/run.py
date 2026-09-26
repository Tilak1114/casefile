"""Run the v2 team on a case: open the claim file, dispatch tasks until it closes or a guard stops it.

Tasks run in parallel threads; a reviewer's work task runs as its LangGraph graph with a MongoDB
checkpointer (thread id = task id). The runner waits on task completion; the MongoDB store also supports
change streams for consumers in other processes.
"""

import sys
import traceback
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime

from langgraph.checkpoint.mongodb import MongoDBSaver
from pydantic import BaseModel

from casefile import db as dbmod
from casefile.case import CaseConfig
from casefile.config import DATA_DIR, settings
from casefile.harness.assemble import assemble
from casefile.harness.examiner import Deps as V1Deps
from casefile.harness.store import RunStore
from casefile.models.openrouter import OpenRouter
from casefile.sources.models import FetchManifest
from casefile.team import context, lead
from casefile.team.desk import RecordsDesk
from casefile.team.dispatcher import Dispatcher
from casefile.team.events import Actor, EventType as E
from casefile.team.llm import ModelGate
from casefile.team.reviewer import REVIEWERS, TeamDeps, WorkState, answer_request, propose_absences, work_graph
from casefile.team.store import MongoStore, Task
from casefile.verify.coverage import CoverageLog
from casefile.verify.load import load_index

MAX_TASKS_AT_ONCE = 4
MAX_CYCLES = 300
MAX_RUN_TOKENS = 8_000_000
STALL_CYCLES = 3  # cycles with nothing running or ready before the lead is told
WORK_EVENTS = {E.COUNSEL_ASSIGNED, E.EXPERT_APPROVED, E.WORK_ASSIGNED}


class RunSummary(BaseModel):
    run_id: str
    stop_reason: str
    cycles: int
    tasks: int
    failed: int
    model_calls: int
    cost_usd: float


def execute(deps: TeamDeps, task: Task, checkpointer: MongoDBSaver) -> str:
    event = next(e for e in deps.dispatcher.store.events() if e.id == task.trigger_event_id)
    if task.role is Actor.LEAD:
        return lead.handle(deps, event, task.id)
    brief = REVIEWERS[task.role]
    if event.type in WORK_EVENTS:
        graph = work_graph(deps, brief).compile(checkpointer=checkpointer)
        focus = event.payload.get("focus") or brief.default_focus
        graph.invoke(WorkState(task_id=task.id, trigger_id=event.id, focus=focus,
                               document_ids=event.payload.get("document_ids", [])),
                     {"configurable": {"thread_id": task.id}, "recursion_limit": 30})
        return "work done"
    if event.type is E.REQUEST_RAISED:
        answer_request(deps, brief, event, task.id)
        return "answered"
    return f"noted {event.type.value}"


def run_team(case_id: str, run_id: str | None = None, allow_spend: bool = False, max_cycles: int = MAX_CYCLES,
             fresh: bool = False) -> RunSummary:
    config = settings()
    client = dbmod.client()
    db = client[config.casefile_database]
    case_dir = DATA_DIR / "cases" / case_id
    run_id = run_id or f"team-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    index = load_index(db, case_id)
    coverage = CoverageLog(db, case_id, run_id)
    store = RunStore(db, case_id, run_id)
    gate = ModelGate(OpenRouter(config.openrouter_api, case_dir / "cache" / "openrouter", allow_spend=allow_spend,
                               read_cache=not fresh), db, run_id)
    dispatcher = Dispatcher(MongoStore(db, run_id), case_id=case_id, run_id=run_id, max_running=MAX_TASKS_AT_ONCE)
    deps = TeamDeps(gate=gate, desk=RecordsDesk(db, index, coverage), index=index, store=store, dispatcher=dispatcher)
    checkpointer = MongoDBSaver(client, db_name=config.casefile_database)

    if not dispatcher.store.events():
        dispatcher.emit(E.CLAIM_FILE_OPENED, Actor.SYSTEM, to=Actor.LEAD,
                        payload={"documents": sum(not d.is_label for d in index.documents.values())})
    running: dict[Future, Task] = {}
    stall = 0
    stop = "cycle limit"
    failed = 0
    with ThreadPoolExecutor(MAX_TASKS_AT_ONCE) as pool:
        for _ in range(max_cycles):
            for task in dispatcher.cycle():
                running[pool.submit(execute, deps, task, checkpointer)] = task
            if running:
                done, _ = wait(list(running), timeout=600, return_when=FIRST_COMPLETED)
                for f in done:
                    task = running.pop(f)
                    try:
                        dispatcher.finish(task.id, note=f.result())
                    except Exception as exc:  # a failed task is recorded and the lead can see it; the run goes on
                        failed += 1
                        dispatcher.fail(task.id, note=f"{type(exc).__name__}: {exc}")
                        traceback.print_exception(exc, file=sys.stderr)
                stall = 0
            else:
                if dispatcher.store.has_event(E.CLAIM_FILE_CLOSED, None):
                    stop = "claim file closed"
                    break
                stall += 1
                if stall == STALL_CYCLES:
                    unfinished = context.unfinished_documents(db, run_id, index)
                    dispatcher.emit(E.GUARD_HIT, Actor.DISPATCHER, to=Actor.LEAD,
                                    payload={"guard": "no progress", "unfinished_documents": len(unfinished)})
                elif stall > STALL_CYCLES * 2:
                    stop = "guard: no progress after telling the lead"
                    break
            spent = gate.spent()
            if spent.get("prompt", 0) + spent.get("output", 0) >= MAX_RUN_TOKENS:
                dispatcher.emit(E.GUARD_HIT, Actor.DISPATCHER, to=Actor.LEAD, payload={"guard": "token budget"})
                stop = "guard: token budget"
                break

    # Closing: each reviewer proposes absences, checked against coverage and search; then assembly by code.
    for actor in (Actor.COUNSEL, Actor.ENGINEER):
        if actor is Actor.COUNSEL or dispatcher.store.has_event(E.EXPERT_APPROVED, None):
            try:
                propose_absences(deps, REVIEWERS[actor], task_id=f"{run_id}-absences-{actor.value}")
            except Exception as exc:
                print(f"absences for {actor.value} failed: {exc}", file=sys.stderr)
    case = CaseConfig.model_validate_json((case_dir / "case.json").read_text())
    manifest = FetchManifest.model_validate_json((case_dir / "fetch_manifest.json").read_text())
    assemble(V1Deps(gemini=None, index=index, store=store, coverage=coverage), case, {f.file_no: f.sha256 for f in manifest.files})
    spent = gate.spent()
    summary = RunSummary(run_id=run_id, stop_reason=stop, cycles=dispatcher.cycle_no, tasks=len(dispatcher.store.tasks()),
                         failed=failed, model_calls=spent.get("calls", 0), cost_usd=round(spent.get("cost", 0.0), 4))
    db.team_runs.replace_one({"_id": run_id}, {"_id": run_id, **summary.model_dump(), "finished_at": datetime.now(UTC)}, upsert=True)
    return summary
