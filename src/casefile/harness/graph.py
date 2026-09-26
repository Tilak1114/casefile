"""The run as a LangGraph loop, checkpointed to MongoDB so it can be stopped and resumed.

decide -> validate -> act -> record -> (decide | wrap_up). All state the run learns lives in MongoDB;
the graph state only counts turns, spawns and progress for the guards.
"""

from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.graph import END, START, StateGraph

from casefile.harness.examiner import (
    MAX_RUN_TOKENS,
    MAX_TURNS,
    MAX_UNPRODUCTIVE_TURNS,
    MAX_WORKER_SPAWNS,
    Deps,
    act,
    decide,
    validate,
)
from casefile.harness.models import Finish, RunState, TraceKind


def run_tokens(deps: Deps) -> int:
    agg = deps.store.db.workers.aggregate([
        {"$match": {"run_id": deps.store.run_id}},
        {"$group": {"_id": None, "t": {"$sum": {"$add": ["$prompt_tokens", "$output_tokens", "$thinking_tokens"]}}}},
    ])
    workers = next(agg, {"t": 0})["t"]
    examiner = sum(e.get("tokens") or 0 for e in deps.store.db.trace.find({"run_id": deps.store.run_id, "kind": "decision"}))
    return workers + examiner


def build_graph(deps: Deps, checkpointer: MongoDBSaver):
    def decide_node(state: RunState) -> dict:
        decision, chars, tokens = decide(deps, state)
        action = decision.action()
        problem = validate(action, deps, state)
        if problem:
            deps.store.trace(state.turn, TraceKind.REJECTED, problem, context_chars=chars, tokens=tokens)
            return {"last_action": action, "last_rejection": problem}
        deps.store.trace(state.turn, TraceKind.DECISION, decision.thinking, action=action, context_chars=chars, tokens=tokens)
        return {"last_action": action, "last_rejection": None}

    def act_node(state: RunState) -> dict:
        if state.last_rejection or state.last_action is None:
            return {}
        if isinstance(state.last_action, Finish):
            return {"done": True, "stop_reason": f"examiner finished: {state.last_action.reason}"}
        workers, summary = act(state.last_action, deps, state)
        deps.store.trace(state.turn, TraceKind.WORKER, summary, action=state.last_action, worker_ids=[w.id for w in workers])
        return {"spawns": state.spawns + len(workers)}

    def record_node(state: RunState) -> dict:
        marker = deps.store.count("findings") + len(deps.store.pages_read())
        unproductive = 0 if marker > state.progress_marker else state.unproductive + 1
        update = {"turn": state.turn + 1, "progress_marker": marker, "unproductive": unproductive}
        if not state.done:
            if state.turn + 1 >= MAX_TURNS:
                update |= {"done": True, "stop_reason": f"guard: {MAX_TURNS} turns"}
            elif unproductive >= MAX_UNPRODUCTIVE_TURNS:
                update |= {"done": True, "stop_reason": f"guard: {MAX_UNPRODUCTIVE_TURNS} turns without progress"}
            elif state.spawns >= MAX_WORKER_SPAWNS and not state.last_rejection:
                update |= {"done": True, "stop_reason": f"guard: {MAX_WORKER_SPAWNS} readers started"}
            elif run_tokens(deps) >= MAX_RUN_TOKENS:
                update |= {"done": True, "stop_reason": f"guard: {MAX_RUN_TOKENS} tokens"}
        deps.store.trace(state.turn, TraceKind.PROGRESS, update.get("stop_reason") or "turn recorded",
                         coverage_pages=len(deps.store.pages_read()), verified_total=deps.store.count("findings"),
                         refused_total=deps.store.count("refusals"), tokens=run_tokens(deps))
        return update

    def route(state: RunState) -> str:
        return "end" if state.done else "decide"

    graph = StateGraph(RunState)
    graph.add_node("decide", decide_node)
    graph.add_node("act", act_node)
    graph.add_node("record", record_node)
    graph.add_edge(START, "decide")
    graph.add_edge("decide", "act")
    graph.add_edge("act", "record")
    graph.add_conditional_edges("record", route, {"decide": "decide", "end": END})
    return graph.compile(checkpointer=checkpointer)


def run_config(run_id: str) -> dict:
    # Each turn is three nodes; the recursion limit is only a backstop behind the turn guard.
    return {"configurable": {"thread_id": run_id}, "recursion_limit": MAX_TURNS * 3 + 10}
