"""The records desk: deterministic, typed, read-only retrieval tools the agents call.

Every tool hides production labels and anything outside the readable claim file (withheld PDFs are never
ingested). Reading and searching write coverage records automatically, with who did it and why. Agents
never query the database directly.
"""

import re
from collections import defaultdict

from pydantic import BaseModel, Field
from pymongo.database import Database

from casefile.search import search_pages
from casefile.verify.coverage import CoverageLog
from casefile.verify.index import CaseIndex, IndexedDocument

# Reference-like codes: letters and digits joined by hyphens or dots ("C09B2-0350", "723.480-014 C"), and
# numbered references ("DR No. 1", "Letter No. 0350"). A code found in many documents (a contract number on
# every letterhead) says nothing about which document is meant, so it is ignored.
CODE = re.compile(r"\b(?=[A-Z0-9.\-]*\d)[A-Z0-9]{2,}(?:[.\-][A-Z0-9]{1,}){1,4}\b")
NUMBERED = re.compile(r"\b((?:DR|RFI|CO|CP|Letter|Submittal|Transmittal|Deficiency Report)\s+No\.?\s*[A-Z0-9\-]+)", re.I)
MAX_DOCS_FOR_A_REFERENCE = 6


class DocumentQuery(BaseModel):
    doc_types: list[str] = []
    date_from: str | None = None
    date_to: str | None = None
    author: str | None = None
    recipient: str | None = None
    file_no: int | None = None
    limit: int = Field(50, le=200)


class DocumentRow(BaseModel):
    id: str
    doc_type: str
    date: str | None
    author: str | None
    recipient: str | None
    pages: int
    file_no: int


class PageText(BaseModel):
    page_id: str
    text: str


class DocumentText(BaseModel):
    document: DocumentRow
    pages: list[PageText]
    coverage_id: str


class SearchHit(BaseModel):
    page_id: str
    document_id: str | None
    score: float
    snippet: str


class Reference(BaseModel):
    code: str
    documents: list[str]  # other documents that carry the same code


class CoverageRow(BaseModel):
    document_id: str
    read_by: list[str]  # actors who read it in full
    focuses: list[str]
    searched: bool


def _row(doc: IndexedDocument, index: CaseIndex) -> DocumentRow:
    m = doc.metadata
    return DocumentRow(id=doc.id, doc_type=doc.doc_type, date=m.date.value if m.date else None,
                       author=m.author_org.value if m.author_org else None,
                       recipient=m.recipient_org.value if m.recipient_org else None,
                       pages=len(doc.page_ids), file_no=index.pages[doc.page_ids[0]].file_no)


def _within(date: str | None, lo: str | None, hi: str | None) -> bool:
    if date is None:
        return lo is None and hi is None
    return (lo is None or date >= lo) and (hi is None or date[: len(hi)] <= hi)


def _codes(text: str) -> set[str]:
    return {c for c in CODE.findall(text) if len(c) >= 6} | {n.strip() for n in NUMBERED.findall(text)}


class RecordsDesk:
    def __init__(self, db: Database, index: CaseIndex, coverage: CoverageLog):
        self.db = db
        self.index = index
        self.coverage = coverage
        self._docs = [d for d in index.documents.values() if not d.is_label]
        self._codes_by_doc: dict[str, set[str]] | None = None

    # ---- the index ------------------------------------------------------------------------------

    def list_documents(self, q: DocumentQuery) -> list[DocumentRow]:
        rows = []
        for d in sorted(self._docs, key=lambda d: (d.date or "9999", d.id)):
            r = _row(d, self.index)
            if q.doc_types and r.doc_type not in q.doc_types:
                continue
            if (q.date_from or q.date_to) and not _within(r.date, q.date_from, q.date_to):
                continue
            if q.author and (not r.author or q.author.lower() not in r.author.lower()):
                continue
            if q.recipient and (not r.recipient or q.recipient.lower() not in r.recipient.lower()):
                continue
            if q.file_no is not None and r.file_no != q.file_no:
                continue
            rows.append(r)
        return rows[: q.limit]

    # ---- reading and searching (write coverage) --------------------------------------------------

    def get_document(self, document_id: str, *, actor: str, focus: str) -> DocumentText:
        doc = self.index.documents.get(document_id)
        if doc is None or doc.is_label:
            raise KeyError(f"{document_id} is not a readable document")
        pages = [PageText(page_id=p, text=self.index.pages[p].text) for p in doc.page_ids if not self.index.pages[p].is_label]
        record = self.coverage.read([p.page_id for p in pages], actor=actor, focus=focus)
        return DocumentText(document=_row(doc, self.index), pages=pages, coverage_id=record.id)

    def search_text(self, query: str, *, actor: str, phrase: bool = False, limit: int = 10) -> list[SearchHit]:
        hits = search_pages(self.db, self.index.case_id, query, limit=limit, phrase=phrase)
        self.coverage.search([h["_id"] for h in hits], query, actor=actor)
        out = []
        for h in hits:
            doc = self.index.document_of(h["_id"])
            snippet = " … ".join("".join(t["value"] for t in hl["texts"]) for hl in h.get("highlights", [])[:2])
            out.append(SearchHit(page_id=h["_id"], document_id=doc.id if doc else None, score=h.get("score", 0.0),
                                 snippet=snippet[:400]))
        return out

    # ---- references between documents -------------------------------------------------------------

    def _code_map(self) -> dict[str, set[str]]:
        if self._codes_by_doc is None:
            self._codes_by_doc = {
                d.id: set().union(*(_codes(self.index.pages[p].text) for p in d.page_ids if p in self.index.pages))
                for d in self._docs
            }
        return self._codes_by_doc

    def find_references(self, document_id: str) -> list[Reference]:
        codes = self._code_map()
        docs_with: dict[str, set[str]] = defaultdict(set)
        for doc_id, cs in codes.items():
            for c in cs:
                docs_with[c].add(doc_id)
        out = []
        for code in sorted(codes.get(document_id, set())):
            others = sorted(docs_with[code] - {document_id})
            if others and len(docs_with[code]) <= MAX_DOCS_FOR_A_REFERENCE:
                out.append(Reference(code=code, documents=others))
        return out

    # ---- what the team knows ----------------------------------------------------------------------

    def coverage_status(self, document_ids: list[str] | None = None) -> list[CoverageRow]:
        records = self.coverage.records().values()
        wanted = document_ids or [d.id for d in self._docs]
        rows = []
        for doc_id in wanted:
            doc = self.index.documents[doc_id]
            pages = set(doc.page_ids)
            reads = [r for r in records if r.mode.value == "read" and pages & set(r.page_ids)]
            rows.append(CoverageRow(document_id=doc_id, read_by=sorted({r.actor or "?" for r in reads}),
                                    focuses=sorted({r.focus for r in reads if r.focus}),
                                    searched=any(r.mode.value == "search" and pages & set(r.page_ids) for r in records)))
        return rows
