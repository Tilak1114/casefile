"""Document metadata (date, author, recipient) read by Gemini, kept only where the source span checks out.

Every field must quote the exact span of the document it was read from. A field whose span is not on
the stated page, or whose value does not appear in its span, is dropped rather than kept unchecked.
"""

import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from pydantic import BaseModel, Field
from pymongo.database import Database

from casefile.ingest.models import page_id
from casefile.models.gemini import Gemini, GeminiUsage
from casefile.verify.index import DocumentMetadata, MetadataField
from casefile.verify.text import FOLD, find_quote

MAX_PARALLEL = 8
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]


class ProposedField(BaseModel):
    value: str = Field(description="The value. Dates as YYYY-MM-DD, or YYYY-MM or YYYY if the day or month is not given.")
    span: str = Field(description="The exact text on the page the value was read from, copied character for character.")
    page_id: str = Field(description="The id of the page the span is on.")


class ProposedMetadata(BaseModel):
    date: ProposedField | None = Field(None, description="The date the document was written or issued.")
    author_org: ProposedField | None = Field(None, description="The organisation that wrote or sent the document, as written in it.")
    recipient_org: ProposedField | None = Field(None, description="The organisation it was addressed to, as written in it.")


PROMPT = """You read one document from a construction project record and report its date, author organisation and recipient organisation.
Rules:
- Use only what is written in the document. If a field is not stated, leave it out.
- For each field give the exact span you read it from, copied character for character, and the id of the page it is on.
- The value of an organisation must be written exactly as it appears inside its span.
- The date is the date the document was written or issued, not dates it mentions.

Document type: {doc_type}
{pages}"""


def date_matches_span(value: str, span: str) -> bool:
    """The span must show the value's year, and its month if the value has one (as a name or a number)."""
    if not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", value):
        return False
    parts = value.split("-")
    text = span.lower()
    year = parts[0]
    if year not in text and not re.search(rf"[/.\- ']{year[2:]}(\D|$)", text):
        return False
    if len(parts) >= 2:
        month = int(parts[1])
        name = MONTHS[month - 1]
        numeric = re.search(rf"(^|\D)0?{month}[/.-]", text)
        if name[:3] not in text and not numeric:
            return False
    return True


def check(proposal: ProposedMetadata, page_texts: dict[str, str]) -> tuple[DocumentMetadata, list[str]]:
    kept: dict[str, MetadataField] = {}
    dropped: list[str] = []
    for name in ("date", "author_org", "recipient_org"):
        field: ProposedField | None = getattr(proposal, name)
        if field is None:
            continue
        text = page_texts.get(field.page_id)
        if text is None or find_quote(text, field.span) is None:
            dropped.append(f"{name}: span not found on {field.page_id}: {field.span!r}")
            continue
        if name == "date":
            ok = date_matches_span(field.value, field.span)
        else:
            ok = field.value.translate(FOLD).lower() in field.span.translate(FOLD).lower()
        if not ok:
            dropped.append(f"{name}: value {field.value!r} does not appear in span {field.span!r}")
            continue
        kept[name] = MetadataField(value=field.value, span=field.span, page_id=field.page_id)
    return DocumentMetadata(**kept), dropped


def extract_one(gemini: Gemini, doc: dict, page_texts: dict[str, str]) -> tuple[DocumentMetadata, list[str], GeminiUsage, bool]:
    pages = "\n\n".join(f"[page {pid}]\n{text}" for pid, text in page_texts.items())
    prompt = PROMPT.format(doc_type=doc["doc_type"], pages=pages)
    proposal, usage, cached = gemini.structured("metadata", prompt, ProposedMetadata)
    meta, dropped = check(proposal, page_texts)
    return meta, dropped, usage, cached


def extract_case(db: Database, case_id: str, gemini: Gemini) -> dict:
    texts = {p["_id"]: p["text"] for p in db.pages.find({"case_id": case_id, "is_label": False})}
    docs = list(db.documents.find({"case_id": case_id, "is_label": False}))
    totals = {"documents": 0, "fields": 0, "dropped": 0, "failed": 0, "cached": 0, "prompt_tokens": 0,
              "output_tokens": 0, "thinking_tokens": 0}
    with ThreadPoolExecutor(MAX_PARALLEL) as pool:
        jobs = {}
        for doc in docs:
            page_texts = {pid: texts[pid] for p in doc["pages"] if (pid := page_id(case_id, doc["file_no"], p)) in texts}
            jobs[pool.submit(extract_one, gemini, doc, page_texts)] = doc
        for job in as_completed(jobs):
            doc = jobs[job]
            try:
                meta, dropped, usage, cached = job.result()
            except Exception as exc:  # report each failure as it happens
                totals["failed"] += 1
                print(f"{doc['_id']}: {exc}", file=sys.stderr, flush=True)
                continue
            db.metadata.replace_one(
                {"_id": doc["_id"]},
                {"_id": doc["_id"], "case_id": case_id, "fields": meta.model_dump(mode="json", exclude_none=True),
                 "dropped": dropped, "model": gemini.model},
                upsert=True,
            )
            totals["documents"] += 1
            totals["fields"] += len(meta.model_dump(exclude_none=True))
            totals["dropped"] += len(dropped)
            totals["cached"] += cached
            for k, v in usage.model_dump().items():
                totals[k] += 0 if cached else v
    return totals
