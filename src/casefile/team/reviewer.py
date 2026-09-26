"""Defense counsel and the forensic engineer: the same graph, different briefs and permissions.

A work task runs plan -> read -> review -> (read | close) as a LangGraph graph, checkpointed per task.
Everything the reviewer learns is written to MongoDB as verified claims and events; the graph state only
carries ids and counters.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from casefile.harness.assemble import check_negative
from casefile.harness.examiner import batches
from casefile.harness.models import NegativesOutput
from casefile.harness.store import RunStore
from casefile.team import context
from casefile.team.desk import RecordsDesk
from casefile.team.dispatcher import Dispatcher
from casefile.team.events import Actor, Event, EventType as E
from casefile.team.llm import ModelGate
from casefile.team.reader import ReadFailed, read
from casefile.team.reservations import reserve
from casefile.team.roles import REVIEWERS, ReviewerBrief
from casefile.verify.index import CaseIndex

MAX_FOLLOW_UP_ROUNDS = 2
MAX_DOCUMENTS_PER_ROUND = 40
READERS_PER_TASK = 8  # readers one task runs at once; the model gate caps the team's total


@dataclass
class TeamDeps:
    gate: ModelGate
    desk: RecordsDesk
    index: CaseIndex
    store: RunStore
    dispatcher: Dispatcher


# ---- what the model returns ----------------------------------------------------------------------

class ReadingPlan(BaseModel):
    thinking: str = Field(description="One or two sentences on why these documents.")
    document_ids: list[str] = Field(description="Documents to read now, from the index.")
    focus: str = Field(description="What to look for in them.")


class FollowUp(BaseModel):
    thinking: str
    read_more: list[str] = Field([], description="Further document ids to read, from the index.")
    searches: list[str] = Field([], description="Search queries for documents not yet found.")
    question_for_other_role: str | None = Field(None, description="A question for the other reviewer, if needed.")
    request_expert: str | None = Field(None, description="Counsel only: the scope for retaining the forensic engineer.")
    done: bool = Field(description="True when this assignment is complete.")


class Report(BaseModel):
    summary: str = Field(description="What the documents show, in a few sentences; facts only.")
    key_claim_ids: list[str] = Field(description="Ids of the verified claims that matter most.")
    open_questions: list[str] = []


class Answer(BaseModel):
    answer: str
    claim_ids: list[str] = Field(description="Verified claim ids that support the answer.")
    not_found: bool = Field(description="True if your verified claims do not answer the question.")


PLAN_PROMPT = """{brief}

Assignment from {sender}: {focus}

Choose the documents to read now (at most {max_docs}). You read whole documents; the index below is all you
see until you read them. Prefer documents nobody has read, and documents your role needs.

Document index (id | type | date | from -> to | pages | read by):
{index}"""

REVIEW_PROMPT = """{brief}

Your assignment: {focus}

Your verified claims so far (id | kind | date | statement):
{claims}

Open questions your readers raised:
{questions}

Documents your readers could not find by reference, and search results, may call for more reading. Decide
the next step. Stop when the assignment is covered.

Document index (id | type | date | from -> to | pages | read by):
{index}"""

REPORT_PROMPT = """{brief}

Write your report to the claim professional on this assignment: {focus}
State facts the records show, citing the ids of your verified claims below. No opinions on fault or cause.

Your verified claims (id | kind | date | statement):
{claims}"""

ANSWER_PROMPT = """{brief}

Another member of the team asks: {question}

Answer only from your verified claims below and cite their ids. If they do not answer it, say so.

Your verified claims (id | kind | date | statement):
{claims}"""

NEGATIVES_PROMPT = """{brief}

State what the claim file does NOT contain that matters to this claim: records one would expect and cannot
find. For each, give the document types and date window, and short phrases that would appear on a page
contradicting it. Each will be checked by searching every page in scope.

Your verified claims:
{claims}

Document index (id | type | date | from -> to | pages | read by):
{index}"""


class WorkState(BaseModel):
    task_id: str
    trigger_id: str
    focus: str
    document_ids: list[str] = []
    round: int = 0
    done: bool = False


def _valid(ids: list[str], deps: TeamDeps) -> list[str]:
    return [i for i in dict.fromkeys(ids) if i in deps.index.documents and not deps.index.documents[i].is_label]


def _read_documents(deps: TeamDeps, brief: ReviewerBrief, doc_ids: list[str], focus: str, task_id: str) -> int:
    """Read the documents this task can reserve; a failed batch is recorded and the rest carry on. Returns failures."""
    db, run = deps.store.db, deps.store.run_id
    held = reserve(db, run, brief.actor.value, doc_ids, task_id)
    todo = [deps.index.documents[i] for i in held]

    def one(group) -> bool:
        try:
            read(gate=deps.gate, desk=deps.desk, index=deps.index, store=deps.store, brief=brief,
                 documents=group, focus=focus, task_id=task_id,
                 claim=lambda ids: reserve(db, run, brief.actor.value, ids, task_id))
            return True
        except ReadFailed as exc:  # recorded; the documents are released so another task can try them
            db.reader_failures.insert_one({"run_id": run, "task_id": task_id, "role": brief.actor.value,
                                           "document_ids": exc.document_ids, "error": str(exc)[:500]})
            db.reservations.delete_many({"_id": {"$in": [f"{run}:{brief.actor.value}:{i}" for i in exc.document_ids]}})
            return False

    with ThreadPoolExecutor(READERS_PER_TASK) as pool:
        return sum(not ok for ok in pool.map(one, batches(todo, deps.index)))


def work_graph(deps: TeamDeps, brief: ReviewerBrief):
    other = Actor.ENGINEER if brief.actor is Actor.COUNSEL else Actor.COUNSEL
    db, run = deps.store.db, deps.store.run_id

    def plan(s: WorkState) -> dict:
        if s.document_ids:
            return {"document_ids": _valid(s.document_ids, deps)[:MAX_DOCUMENTS_PER_ROUND]}
        out, _ = deps.gate.call(actor=brief.actor.value, purpose="plan", schema=ReadingPlan, task_id=s.task_id,
                                prompt=PLAN_PROMPT.format(brief=brief.brief, sender="the claim professional", focus=s.focus,
                                                          max_docs=MAX_DOCUMENTS_PER_ROUND, index=context.document_index(db, run, deps.index)))
        return {"document_ids": _valid(out.document_ids, deps)[:MAX_DOCUMENTS_PER_ROUND], "focus": out.focus or s.focus}

    def read_node(s: WorkState) -> dict:
        _read_documents(deps, brief, s.document_ids, s.focus, s.task_id)
        return {"round": s.round + 1}

    def review(s: WorkState) -> dict:
        if s.round > MAX_FOLLOW_UP_ROUNDS:
            return {"done": True}
        out, _ = deps.gate.call(actor=brief.actor.value, purpose="review", schema=FollowUp, task_id=s.task_id,
                                prompt=REVIEW_PROMPT.format(brief=brief.brief, focus=s.focus,
                                                            claims=context.own_claims(db, run, brief.claim_role.value),
                                                            questions="\n".join(f"- {q}" for q in context.open_questions(db, run, brief.claim_role.value)) or "(none)",
                                                            index=context.document_index(db, run, deps.index)))
        more = _valid(out.read_more, deps)
        for q in out.searches[:3]:
            more += [h.document_id for h in deps.desk.search_text(q, actor=brief.actor.value) if h.document_id]
        if out.question_for_other_role:
            deps.dispatcher.emit(E.REQUEST_RAISED, brief.actor, to=other, causation_id=s.trigger_id,
                                 payload={"question": out.question_for_other_role})
        if out.request_expert and brief.actor is Actor.COUNSEL:
            deps.dispatcher.emit(E.EXPERT_REQUESTED, Actor.COUNSEL, to=Actor.LEAD, causation_id=s.trigger_id,
                                 payload={"scope": out.request_expert})
        more = _valid(more, deps)[:MAX_DOCUMENTS_PER_ROUND]
        return {"document_ids": more, "done": out.done or not more}

    def close(s: WorkState) -> dict:
        claims = context.own_claims(db, run, brief.claim_role.value)
        report, _ = deps.gate.call(actor=brief.actor.value, purpose="report", schema=Report, task_id=s.task_id,
                                   prompt=REPORT_PROMPT.format(brief=brief.brief, focus=s.focus, claims=claims))
        known = {c["_id"] for c in db.findings.find({"run_id": run, "_id": {"$in": report.key_claim_ids}}, {"_id": 1})}
        deps.dispatcher.emit(E.REPORT_SUBMITTED, brief.actor, to=Actor.LEAD, causation_id=s.trigger_id,
                             subject_ids=sorted(known), payload={"summary": report.summary, "open_questions": report.open_questions,
                                                                 "uncited_ids_dropped": len(report.key_claim_ids) - len(known)})
        open_disputes(deps, brief)
        return {}

    g = StateGraph(WorkState)
    g.add_node("plan", plan)
    g.add_node("read", read_node)
    g.add_node("review", review)
    g.add_node("close", close)
    g.add_edge(START, "plan")
    g.add_edge("plan", "read")
    g.add_edge("read", "review")
    g.add_conditional_edges("review", lambda s: "close" if s.done else "read", {"close": "close", "read": "read"})
    g.add_edge("close", END)
    return g


def open_disputes(deps: TeamDeps, brief: ReviewerBrief) -> int:
    """Deterministic: a verified event of this role and one of the other role on the same page with different dates."""
    db, run = deps.store.db, deps.store.run_id
    other = "engineer" if brief.claim_role.value == "counsel" else "counsel"
    mine = list(db.findings.find({"run_id": run, "role": brief.claim_role.value, "kind": "event"}))
    theirs = list(db.findings.find({"run_id": run, "role": other, "kind": "event"}))
    opened = 0
    for a in mine:
        pa = {q["page_id"] for q in a.get("citations", [])}
        for b in theirs:
            if pa & {q["page_id"] for q in b.get("citations", [])} and a.get("date") and b.get("date") \
                    and not a["date"].startswith(b["date"]) and not b["date"].startswith(a["date"]) \
                    and _similar(a["statement"], b["statement"]):
                key = "|".join(sorted([a["_id"], b["_id"]]))
                if db.disputes.count_documents({"_id": key}, limit=1):
                    continue
                db.disputes.insert_one({"_id": key, "run_id": run, "claims": [a["_id"], b["_id"]], "status": "open",
                                        "about": "meaning", "question": "Which date does the record support?"})
                deps.dispatcher.emit(E.DISPUTE_OPENED, brief.actor, to=Actor.LEAD, subject_ids=[a["_id"], b["_id"]],
                                     correlation_id=f"dispute-{key}", payload={"dispute_id": key, "about": "meaning",
                                                                               "question": "Which date does the record support?"})
                opened += 1
    return opened


def _similar(x: str, y: str) -> bool:
    wx = {w for w in x.lower().split() if len(w) > 3}
    wy = {w for w in y.lower().split() if len(w) > 3}
    return bool(wx and wy) and len(wx & wy) / min(len(wx), len(wy)) >= 0.5


def answer_request(deps: TeamDeps, brief: ReviewerBrief, event: Event, task_id: str) -> None:
    db, run = deps.store.db, deps.store.run_id
    out, _ = deps.gate.call(actor=brief.actor.value, purpose="answer", schema=Answer, task_id=task_id,
                            prompt=ANSWER_PROMPT.format(brief=brief.brief, question=event.payload.get("question", ""),
                                                        claims=context.own_claims(db, run, brief.claim_role.value)))
    known = [c["_id"] for c in db.findings.find({"run_id": run, "_id": {"$in": out.claim_ids}}, {"_id": 1})]
    deps.dispatcher.emit(E.REQUEST_ANSWERED, brief.actor, to=event.sender, correlation_id=event.correlation_id,
                         causation_id=event.id, subject_ids=known,
                         payload={"answer": out.answer if known or out.not_found else "not answered with verified claims",
                                  "not_found": out.not_found or not known})


def propose_absences(deps: TeamDeps, brief: ReviewerBrief, task_id: str) -> tuple[int, int]:
    db, run = deps.store.db, deps.store.run_id
    out, _ = deps.gate.call(actor=brief.actor.value, purpose="absences", schema=NegativesOutput, task_id=task_id,
                            prompt=NEGATIVES_PROMPT.format(brief=brief.brief, claims=context.own_claims(db, run, brief.claim_role.value),
                                                           index=context.document_index(db, run, deps.index)))
    from casefile.harness.examiner import Deps as V1Deps  # check_negative reads index, store and coverage from it
    v1 = V1Deps(gemini=None, index=deps.index, store=deps.store, coverage=deps.desk.coverage)
    records = deps.desk.coverage.records()
    ok = bad = 0
    for absence in out.absences:
        deps.dispatcher.emit(E.ABSENCE_PROPOSED, brief.actor, to=None, payload=absence.model_dump())
        claim = check_negative(absence, v1, records).model_copy(update={"role": brief.claim_role})
        deps.store.save_claims([claim])
        deps.dispatcher.emit(E.ABSENCE_CHECKED, Actor.VERIFIER, to=brief.actor, subject_ids=[claim.id],
                             payload={"verified": claim.verified, "reasons": claim.reasons})
        ok += claim.verified
        bad += not claim.verified
    return ok, bad


__all__ = ["REVIEWERS", "TeamDeps", "WorkState", "work_graph", "answer_request", "propose_absences", "open_disputes"]
