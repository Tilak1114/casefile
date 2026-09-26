"""The v2 reader: reads whole documents for a role, with narrow retrieval and one automatic repair.

Narrow retrieval is deterministic: before the model runs, the records desk attaches up to two documents the
batch cites by reference number and the role has not read yet. The harness logs every page given to the
model as read, with the role and focus, before the model runs. A refused claim is retried once, with its page
text and the verifier's reason in front of the model.
"""

import time
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


def _attach(desk: RecordsDesk, batch: list[IndexedDocument], already_read: set[str]) -> list[str]:
    ids = {d.id for d in batch}
    found: list[str] = []
    for d in batch:
        for ref in desk.find_references(d.id):
            for other in ref.documents:
                if other not in ids and other not in already_read and other not in found:
                    found.append(other)
    return found[:MAX_ATTACHED_REFERENCES]


def read(*, gate: ModelGate, desk: RecordsDesk, index: CaseIndex, store: RunStore, brief: ReviewerBrief,
         documents: list[IndexedDocument], focus: str, already_read: set[str], task_id: str | None = None) -> ReaderResult:
    worker_id = f"w-{uuid4().hex[:10]}"
    attached = _attach(desk, documents, already_read)
    all_docs = documents + [index.documents[a] for a in attached]
    text, page_ids = render_documents(all_docs, index)
    record = desk.coverage.read(page_ids, actor=f"{brief.actor.value} reader", focus=focus)
    started = time.time()
    prompt = READER_PROMPT.format(role_brief=brief.brief, focus=focus, documents=text)
    output, usage = gate.call(actor=f"{brief.actor.value}-reader", purpose="read", prompt=prompt, schema=ReaderOutput, task_id=task_id)
    claims = check_output(output, index, run_id=store.run_id, case_id=store.case_id, role=brief.claim_role, worker_id=worker_id)

    refused = [c for c in claims if not c.verified]
    repaired: list[StoredClaim] = []
    if refused:
        pages = {q.page_id for c in refused for q in c.citations}
        docs = [d for d in all_docs if pages & set(d.page_ids)] or all_docs
        doc_text, _ = render_documents(docs, index)
        listing = "\n".join(f"- {c.statement} -- {'; '.join(c.reasons)}" for c in refused)
        fix, fix_usage = gate.call(actor=f"{brief.actor.value}-reader", purpose="repair", schema=ReaderOutput, task_id=task_id,
                                   prompt=REPAIR_PROMPT.format(brief=brief.brief, refused=listing, documents=doc_text))
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
