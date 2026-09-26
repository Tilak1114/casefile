"""The reader: a short-lived worker a role starts to read whole documents and return quoted claims.

The harness, not the model, records coverage: the pages the reader was given are logged as read before
the model is called, whatever it returns.
"""

import threading
import time
from uuid import uuid4

from casefile.harness.checks import check_output
from casefile.harness.models import ReaderOutput, Role, StoredClaim, WorkerRecord
from casefile.harness.roles import ROLES
from casefile.harness.store import RunStore
from casefile.models.gemini import Gemini
from casefile.verify.coverage import CoverageLog
from casefile.verify.index import CaseIndex, IndexedDocument

MAX_WORKERS_ACTIVE = 4
_slots = threading.BoundedSemaphore(MAX_WORKERS_ACTIVE)

READER_PROMPT = """{role_brief}

You are reading the documents below in full. Your focus: {focus}

Rules:
- Report only what the documents say. No opinions about cause, fault or liability.
- Every claim needs quotes copied character for character from the page text, with the id of the page
  each quote is on. Quote 5 to 40 words. Do not fix spelling, capitals or punctuation.
- Events: use date_source "document_date" when the event is the document itself being written or sent;
  "stated_in_text" when the text says when something happened, and then one quote must show that date.
- Parties and relationships: write names exactly as they appear in your quotes. Report aliases only when
  one quote shows both names for the same party (for example "Bechtel/Parsons Brinckerhoff (B/PB)").
- Open questions: documents or facts referred to here that are not among these documents.

{documents}"""


def _document_header(doc: IndexedDocument) -> str:
    meta = doc.metadata
    parts = [f"type: {doc.doc_type}"]
    if meta.date:
        parts.append(f"date: {meta.date.value}")
    if meta.author_org:
        parts.append(f"from: {meta.author_org.value}")
    if meta.recipient_org:
        parts.append(f"to: {meta.recipient_org.value}")
    return f"=== document {doc.id} ({', '.join(parts)}) ==="


def render_documents(docs: list[IndexedDocument], index: CaseIndex) -> tuple[str, list[str]]:
    blocks, page_ids = [], []
    for doc in docs:
        blocks.append(_document_header(doc))
        for pid in doc.page_ids:
            page = index.pages.get(pid)
            if page is None or page.is_label:
                continue
            page_ids.append(pid)
            blocks.append(f"[page {pid}]\n{page.text}")
    return "\n\n".join(blocks), page_ids


def run_reader(
    *, gemini: Gemini, index: CaseIndex, store: RunStore, coverage: CoverageLog, role: Role,
    documents: list[IndexedDocument], focus: str, repair_note: str = "", repair_of: str | None = None,
) -> tuple[WorkerRecord, list[StoredClaim]]:
    worker_id = f"w-{uuid4().hex[:10]}"
    text, page_ids = render_documents(documents, index)
    record = coverage.read(page_ids)  # logged by the harness before the model runs
    prompt = READER_PROMPT.format(role_brief=ROLES[role].brief, focus=focus, documents=text)
    if repair_note:
        prompt += f"\n\nA previous claim from these pages was refused: {repair_note}\nReturn a corrected claim, or nothing if the pages do not support it."
    started = time.time()
    with _slots:
        output, usage, cached = gemini.structured(f"reader-{role.value}", prompt, ReaderOutput)
    claims = check_output(output, index, run_id=store.run_id, case_id=store.case_id, role=role,
                          worker_id=worker_id, repair_of=repair_of)
    verified, refused = store.save_claims(claims)
    worker = WorkerRecord(
        id=worker_id, run_id=store.run_id, role=role, document_ids=[d.id for d in documents], page_ids=page_ids,
        focus=focus, coverage_id=record.id, verified=verified, refused=refused, open_questions=output.open_questions,
        prompt_tokens=usage.prompt_tokens, output_tokens=usage.output_tokens, thinking_tokens=usage.thinking_tokens,
        cached=cached, seconds=round(time.time() - started, 2),
    )
    store.save_worker(worker)
    return worker, claims
