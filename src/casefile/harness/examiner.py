"""The claims examiner: builds its context from MongoDB, decides one action, and the harness carries it out.

The examiner never sees page text or file names. Its actions are checked before they run; a rejected
action is reported back with the reason, not repaired silently.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from casefile.harness.models import (
    Assign,
    ExaminerDecision,
    Finish,
    Repair,
    Role,
    RunState,
    SearchAction,
    StoredClaim,
    TraceKind,
    WorkerRecord,
)
from casefile.harness.reader import MAX_WORKERS_ACTIVE, run_reader
from casefile.harness.roles import ROLES
from casefile.harness.store import RunStore
from casefile.models.gemini import Gemini
from casefile.search import search_pages
from casefile.verify.coverage import CoverageLog
from casefile.verify.index import CaseIndex, IndexedDocument

MAX_TURNS = 40
MAX_WORKER_SPAWNS = 150
MAX_REPAIRS_PER_ACTION = 6
MAX_UNPRODUCTIVE_TURNS = 3
MAX_RUN_TOKENS = 8_000_000
PAGES_PER_READER = 25
SEARCH_HITS = 8


@dataclass
class Deps:
    gemini: Gemini
    index: CaseIndex
    store: RunStore
    coverage: CoverageLog


# ---- context -----------------------------------------------------------------------------------

EXAMINER_PROMPT = """You are the claims examiner leading the investigation of a construction claim. You own the file:
you plan the work, assign it to your reviewers, follow up gaps, and decide when the file is complete.
You never read documents yourself; your reviewers do, and every claim they make is checked against the
page it quotes before it counts.

Your reviewers:
- parties_reviewer: {parties}
- technical_reviewer: {technical}

Goal: every document read by at least one reviewer, open questions followed up by search where the
case file might answer them, refused claims repaired where possible, then finish.

Choose exactly one action:
- assign: give a reviewer documents to read, with a focus;
- search: have a reviewer search the case file for an open question and read what it finds;
- repair: send refused claims back to be corrected (each claim at most once);
- finish: only when every document has been read.

Documents (id | type | date | from -> to | pages | read by):
{documents}

Progress: turn {turn} of {max_turns}; pages read {pages_read} of {pages_total}; verified claims {verified};
refused {refused} ({repairable} not yet repaired); readers started {spawns} of {max_spawns}.

Open questions raised by readers (newest first):
{questions}

Refused claims not yet repaired (newest first):
{refusals}

{last}"""


def _doc_line(doc: IndexedDocument, read_by: dict[str, set[str]]) -> str:
    m = doc.metadata
    date = m.date.value if m.date else "?"
    frm = m.author_org.value if m.author_org else "?"
    to = m.recipient_org.value if m.recipient_org else "?"
    who = ",".join(sorted(r.split("_")[0] for r in read_by.get(doc.id, set()))) or "-"
    return f"{doc.id} | {doc.doc_type} | {date} | {frm} -> {to} | {len(doc.page_ids)} | {who}"


def readable_documents(index: CaseIndex) -> list[IndexedDocument]:
    return sorted((d for d in index.documents.values() if not d.is_label), key=lambda d: d.id)


def read_by(deps: Deps) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for w in deps.store.db.workers.find({"run_id": deps.store.run_id}, {"role": 1, "document_ids": 1}):
        for d in w["document_ids"]:
            result.setdefault(d, set()).add(w["role"])
    return result


def build_context(deps: Deps, state: RunState) -> str:
    db, run_id = deps.store.db, deps.store.run_id
    docs = readable_documents(deps.index)
    who = read_by(deps)
    pages_total = sum(len([p for p in d.page_ids if not deps.index.pages[p].is_label]) for d in docs)
    questions: list[str] = []
    for w in db.workers.find({"run_id": run_id}).sort("_id", -1):
        for q in w["open_questions"]:
            if q not in questions:
                questions.append(q)
    repairable = list(db.refusals.find({"run_id": run_id, "repair_attempted": {"$ne": True}}).sort("created_at", -1))
    last = ""
    if state.last_rejection:
        last = f"Your last action was rejected: {state.last_rejection}"
    elif state.last_action:
        last = f"Your last action: {state.last_action.model_dump_json()}"
    return EXAMINER_PROMPT.format(
        parties=ROLES[Role.PARTIES].default_focus, technical=ROLES[Role.TECHNICAL].default_focus,
        documents="\n".join(_doc_line(d, who) for d in docs), turn=state.turn + 1, max_turns=MAX_TURNS,
        pages_read=len(deps.store.pages_read()), pages_total=pages_total, verified=deps.store.count("findings"),
        refused=deps.store.count("refusals"), repairable=len(repairable), spawns=state.spawns,
        max_spawns=MAX_WORKER_SPAWNS, questions="\n".join(f"- {q}" for q in questions[:12]) or "(none)",
        refusals="\n".join(f"- {r['_id']}: {r['statement'][:80]} -- {r['reasons'][0][:100]}" for r in repairable[:10]) or "(none)",
        last=last,
    )


# ---- validation ----------------------------------------------------------------------------------


def validate(action, deps: Deps, state: RunState) -> str | None:
    """None if the action may run, else the reason it is rejected."""
    if action is None:
        return "choose exactly one action"
    if isinstance(action, Assign):
        unknown = [d for d in action.document_ids if d not in deps.index.documents or deps.index.documents[d].is_label]
        if unknown:
            return f"not readable documents: {unknown[:5]}"
    if isinstance(action, Repair):
        known = {r["_id"] for r in deps.store.db.refusals.find(
            {"run_id": deps.store.run_id, "_id": {"$in": action.refusal_ids}, "repair_attempted": {"$ne": True}})}
        missing = [r for r in action.refusal_ids if r not in known]
        if missing:
            return f"not refused claims awaiting repair: {missing[:5]}"
    if isinstance(action, (Assign, SearchAction, Repair)) and state.spawns >= MAX_WORKER_SPAWNS:
        return f"no readers left: {MAX_WORKER_SPAWNS} already started"
    if isinstance(action, Finish):
        who = read_by(deps)
        unread = [d.id for d in readable_documents(deps.index) if d.id not in who]
        if unread:
            return f"{len(unread)} documents have not been read yet, e.g. {unread[:5]}"
    return None


# ---- actions ---------------------------------------------------------------------------------------


def batches(docs: list[IndexedDocument], pages_per_reader: int = PAGES_PER_READER) -> list[list[IndexedDocument]]:
    """Whole documents grouped into readers of about `pages_per_reader` pages; a long document reads alone."""
    out: list[list[IndexedDocument]] = []
    current: list[IndexedDocument] = []
    size = 0
    for doc in docs:
        n = len(doc.page_ids)
        if current and size + n > pages_per_reader:
            out.append(current)
            current, size = [], 0
        current.append(doc)
        size += n
    if current:
        out.append(current)
    return out


def _run_readers(deps: Deps, role: Role, groups: list[list[IndexedDocument]], focus: str,
                 notes: list[tuple[str, str]] | None = None) -> list[WorkerRecord]:
    with ThreadPoolExecutor(MAX_WORKERS_ACTIVE) as pool:
        jobs = []
        for i, group in enumerate(groups):
            note, repair_of = notes[i] if notes else ("", None)
            jobs.append(pool.submit(run_reader, gemini=deps.gemini, index=deps.index, store=deps.store,
                                    coverage=deps.coverage, role=role, documents=group, focus=focus,
                                    repair_note=note, repair_of=repair_of))
        return [j.result()[0] for j in jobs]


def act(action, deps: Deps, state: RunState) -> tuple[list[WorkerRecord], str]:
    budget = MAX_WORKER_SPAWNS - state.spawns
    if isinstance(action, Assign):
        who = read_by(deps)
        docs = [deps.index.documents[d] for d in action.document_ids if action.role.value not in who.get(d, set())]
        groups = batches(docs)[:budget]
        workers = _run_readers(deps, action.role, groups, action.focus)
        return workers, f"{action.role.value} read {sum(len(g) for g in groups)} documents with {len(groups)} readers"
    if isinstance(action, SearchAction):
        hits = search_pages(deps.store.db, deps.index.case_id, action.query, limit=SEARCH_HITS)
        record = deps.coverage.search([h["_id"] for h in hits], action.query)
        who = read_by(deps)
        doc_ids = []
        for h in hits:
            doc = deps.index.document_of(h["_id"])
            if doc and doc.id not in doc_ids and action.role.value not in who.get(doc.id, set()):
                doc_ids.append(doc.id)
        groups = batches([deps.index.documents[d] for d in doc_ids])[:budget]
        workers = _run_readers(deps, action.role, groups, action.reason) if groups else []
        deps.store.trace(state.turn, TraceKind.SEARCH, f"search {action.query!r}: {len(hits)} pages, {len(doc_ids)} new documents",
                         action=action)
        return workers, f"search {action.query!r} found {len(hits)} pages (coverage {record.id}); {len(doc_ids)} documents not yet read by {action.role.value}"
    if isinstance(action, Repair):
        refusals = [StoredClaim.model_validate(r) for r in deps.store.db.refusals.find(
            {"run_id": deps.store.run_id, "_id": {"$in": action.refusal_ids[:MAX_REPAIRS_PER_ACTION]}})]
        groups, notes = [], []
        for r in refusals[:budget]:
            docs = {deps.index.document_of(c.page_id).id for c in r.citations if deps.index.document_of(c.page_id)}
            if not docs:
                continue
            groups.append([deps.index.documents[d] for d in sorted(docs)])
            notes.append((f"{r.statement} -- refused because: {'; '.join(r.reasons)}", r.id))
            deps.store.db.refusals.update_one({"_id": r.id}, {"$set": {"repair_attempted": True}})
        workers = []
        for role in (Role.PARTIES, Role.TECHNICAL):
            idx = [i for i, r in enumerate(refusals[: len(groups)]) if r.role is role]
            if idx:
                workers += _run_readers(deps, role, [groups[i] for i in idx], "correct the refused claim",
                                        [notes[i] for i in idx])
        return workers, f"repair attempted for {len(groups)} refused claims"
    return [], "finish"


def decide(deps: Deps, state: RunState) -> tuple[ExaminerDecision, int, int]:
    """The examiner's decision, the size of its context, and tokens used (0 when cached)."""
    context = build_context(deps, state)
    decision, usage, cached = deps.gemini.structured("examiner", context, ExaminerDecision)
    tokens = 0 if cached else usage.prompt_tokens + usage.output_tokens + usage.thinking_tokens
    return decision, len(context), tokens
