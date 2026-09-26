"""The v2 reader: reads whole documents for a role, with narrow retrieval and one automatic repair.

Narrow retrieval is deterministic: before the model runs, the records desk attaches up to two documents the
batch cites by reference number, if they are short and the role can reserve them (so no other task of the role
has read or is reading them). The harness logs every page given to the model as read, with the role and focus,
before the model runs. A refused claim is retried once, with its page
text and the verifier's reason in front of the model.
"""

import time
from collections.abc import Callable
from uuid import uuid4

from pydantic import BaseModel

from casefile.harness.checks import check_output
from casefile.harness.models import ReaderOutput, StoredClaim, WorkerRecord
from casefile.harness.reader import READER_PROMPT, render_documents
from casefile.harness.store import RunStore
from casefile.team.desk import RecordsDesk
from casefile.team.llm import ModelGate
from casefile.team.roles import ReviewerBrief
from casefile.verify.index import CaseIndex, IndexedDocument

MAX_ATTACHED_REFERENCES = 2
MAX_ATTACHED_PAGES = 30  # a long referenced report is assigned on its own, not attached to someone else's batch

REPAIR_PROMPT = """{brief}

These claims you made were refused by the verifier, which checks every quote against the page character for
character. For each one, read the page text below and either return a corrected claim whose quotes are copied
exactly from the page, or leave it out if the page does not support it. Return only corrected claims.

Refused claims and the verifier's reasons:
{refused}

{documents}"""


class ReaderResult(BaseModel):
    worker_id: str
    document_ids: list[str]
    attached: list[str]
    page_ids: list[str]
    claims: list[StoredClaim]
    repaired: int
    open_questions: list[str]


class ReadFailed(RuntimeError):
    """A reader batch failed; `document_ids` are every document it held, attached ones included, and
    `coverage_ids` the reads it logged, which the caller removes so the pages count as unread again."""

    def __init__(self, document_ids: list[str], cause: Exception, coverage_ids: list[str] | None = None):
        super().__init__(f"{type(cause).__name__}: {cause}")
        self.document_ids = document_ids
        self.coverage_ids = coverage_ids or []


def _attach(desk: RecordsDesk, index: CaseIndex, batch: list[IndexedDocument],
            claim: Callable[[list[str]], list[str]]) -> list[str]:
    """Referenced documents to read alongside the batch: short ones this reader's role can still reserve."""
    ids = {d.id for d in batch}
    candidates: list[str] = []
    for d in batch:
        for ref in desk.find_references(d.id):
            for other in ref.documents:
                doc = index.documents.get(other)
                if (other not in ids and other not in candidates and doc is not None and not doc.is_label
                        and len(doc.page_ids) <= MAX_ATTACHED_PAGES):
                    candidates.append(other)
    held: list[str] = []
    for other in candidates:
        if len(held) == MAX_ATTACHED_REFERENCES:
            break
        held += claim([other])
    return held


def read(*, gate: ModelGate, desk: RecordsDesk, index: CaseIndex, store: RunStore, brief: ReviewerBrief,
         documents: list[IndexedDocument], focus: str, claim: Callable[[list[str]], list[str]],
         task_id: str | None = None) -> ReaderResult:
    """`claim` reserves documents for this reader's role and returns those it now holds."""
    worker_id = f"w-{uuid4().hex[:10]}"
    attached = _attach(desk, index, documents, claim)
    logged: list[str] = []
    try:
        return _read(gate, desk, index, store, brief, documents, attached, focus, task_id, worker_id, logged)
    except Exception as exc:
        raise ReadFailed([d.id for d in documents] + attached, exc, logged) from exc


def _read(gate: ModelGate, desk: RecordsDesk, index: CaseIndex, store: RunStore, brief: ReviewerBrief,
          documents: list[IndexedDocument], attached: list[str], focus: str, task_id: str | None,
          worker_id: str, logged: list[str]) -> ReaderResult:
    all_docs = documents + [index.documents[a] for a in attached]
    text, page_ids = render_documents(all_docs, index)
    record = desk.coverage.read(page_ids, actor=f"{brief.actor.value} reader", focus=focus)
    logged.append(record.id)
    started = time.time()
    prompt = READER_PROMPT.format(role_brief=brief.brief, focus=focus, documents=text)
    output, usage = gate.call(actor=f"{brief.actor.value}-reader", purpose="read", prompt=prompt, schema=ReaderOutput, task_id=task_id,
                              ref=worker_id)
    claims = check_output(output, index, run_id=store.run_id, case_id=store.case_id, role=brief.claim_role, worker_id=worker_id)

    refused = [c for c in claims if not c.verified]
    repaired: list[StoredClaim] = []
    if refused:
        pages = {q.page_id for c in refused for q in c.citations}
        docs = [d for d in all_docs if pages & set(d.page_ids)] or all_docs
        doc_text, _ = render_documents(docs, index)
        listing = "\n".join(f"- {c.statement} -- {'; '.join(c.reasons)}" for c in refused)
        fix, fix_usage = gate.call(actor=f"{brief.actor.value}-reader", purpose="repair", schema=ReaderOutput, task_id=task_id,
                                   prompt=REPAIR_PROMPT.format(brief=brief.brief, refused=listing, documents=doc_text),
                                   ref=worker_id)
        usage.prompt_tokens += fix_usage.prompt_tokens
        usage.output_tokens += fix_usage.output_tokens
        usage.cost_usd += fix_usage.cost_usd
        def original(c: StoredClaim) -> str | None:
            pages = {q.page_id for q in c.citations}
            return next((r.id for r in refused if pages & {q.page_id for q in r.citations}), None)

        repaired = [c.model_copy(update={"repair_of": original(c)}) for c in
                    check_output(fix, index, run_id=store.run_id, case_id=store.case_id, role=brief.claim_role,
                                 worker_id=worker_id) if c.verified]

    kept = claims + repaired
    verified, refused_n = store.save_claims(kept)
    if refused:
        store.db.refusals.update_many({"_id": {"$in": [c.id for c in refused]}}, {"$set": {"repair_attempted": True}})
    store.save_worker(WorkerRecord(
        id=worker_id, run_id=store.run_id, role=brief.claim_role, document_ids=[d.id for d in all_docs], page_ids=page_ids,
        focus=focus, coverage_id=record.id, verified=verified, refused=refused_n, open_questions=output.open_questions,
        prompt_tokens=usage.prompt_tokens, output_tokens=usage.output_tokens, thinking_tokens=usage.reasoning_tokens,
        cached=False, seconds=round(time.time() - started, 2),
    ))
    return ReaderResult(worker_id=worker_id, document_ids=[d.id for d in documents], attached=attached, page_ids=page_ids,
                        claims=kept, repaired=len(repaired), open_questions=output.open_questions)
