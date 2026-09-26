"""Decide whether a claim may be shown as fact.

A positive claim is verified only if every citation's quote is found on a readable, non-label page and
every typed field it asserts agrees with the cited document's metadata. A negative claim is verified only
if full-text reads cover every page of every document in its scope. Failing claims are refused, not
softened; uncited claims are marked as interpretation.
"""

from casefile.verify.index import CaseIndex, IndexedDocument
from casefile.verify.models import (
    AssertedFields,
    Claim,
    CoverageMode,
    CoverageRecord,
    MatchedQuote,
    NegativeClaim,
    Status,
    Verdict,
)
from casefile.verify.text import FOLD, find_quote


def _same_org(asserted: str, recorded: str) -> bool:
    """The asserted organisation must appear within the recorded one (case-insensitive)."""
    a = " ".join(asserted.translate(FOLD).lower().split())
    r = " ".join(recorded.translate(FOLD).lower().split())
    return bool(a) and a in r


def _check_fields(asserted: AssertedFields, doc: IndexedDocument) -> list[str]:
    problems = []
    if asserted.doc_type and asserted.doc_type != doc.doc_type:
        problems.append(f"document type is {doc.doc_type}, not {asserted.doc_type}")
    if asserted.date:
        if doc.date is None:
            problems.append(f"the cited document has no date in its metadata; cannot confirm {asserted.date}")
        elif not doc.date.startswith(asserted.date):
            # A coarser assertion (1999-10) of a known date (1999-10-07) is fine; anything else is not.
            problems.append(f"date is {doc.date}, not {asserted.date}")
    for field in ("author_org", "recipient_org"):
        value = getattr(asserted, field)
        if not value:
            continue
        recorded = getattr(doc.metadata, field)
        label = field.replace("_org", "")
        if recorded is None:
            problems.append(f"the cited document has no {label} in its metadata; cannot confirm {value}")
        elif not _same_org(value, recorded.value):
            problems.append(f"{label} is {recorded.value}, not {value}")
    return problems


def verify_claim(claim: Claim, index: CaseIndex) -> Verdict:
    if not claim.citations:
        return Verdict(claim_id=claim.id, status=Status.INTERPRETATION, reasons=["no citation"])
    reasons: list[str] = []
    matches: list[MatchedQuote] = []
    for citation in claim.citations:
        page = index.pages.get(citation.page_id)
        if page is None:
            reasons.append(f"{citation.page_id} is not a readable page of this case")
            continue
        if page.is_label:
            reasons.append(f"{citation.page_id} is a production label, which is never evidence")
            continue
        found = find_quote(page.text, citation.quote)
        if found is None:
            reasons.append(f"quote not found on {citation.page_id}: {citation.quote!r}")
            continue
        matches.append(MatchedQuote(page_id=citation.page_id, start=found[0], end=found[1]))
        doc = index.document_of(citation.page_id)
        if doc is not None:
            reasons.extend(_check_fields(claim.asserted, doc))
        elif claim.asserted != AssertedFields():
            reasons.append(f"{citation.page_id} belongs to no document; its fields cannot be confirmed")
    status = Status.REFUSED if reasons else Status.VERIFIED
    return Verdict(claim_id=claim.id, status=status, reasons=reasons, matches=matches)


def _bounds(date: str) -> tuple[str, str]:
    """A partial date as the first and last day it could mean, for comparison as strings."""
    parts = date.split("-")
    start = "-".join(parts + ["01"] * (3 - len(parts)))
    end = "-".join(parts + (["12", "31"] if len(parts) == 1 else ["31"] if len(parts) == 2 else []))
    return start, end


def _in_window(doc: IndexedDocument, date_from: str | None, date_to: str | None) -> bool:
    if doc.date is None:
        return True  # an undated document might fall in the window, so it must be read
    start, end = _bounds(doc.date)
    if date_from and end < _bounds(date_from)[0]:
        return False
    if date_to and start > _bounds(date_to)[1]:
        return False
    return True


def verify_negative(claim: NegativeClaim, index: CaseIndex, coverage: dict[str, CoverageRecord]) -> Verdict:
    unknown = [c for c in claim.coverage_ids if c not in coverage]
    if unknown:
        return Verdict(claim_id=claim.id, status=Status.REFUSED, reasons=[f"unknown coverage record {c}" for c in unknown])
    scope = claim.scope
    in_scope = [
        doc for doc in index.documents.values()
        if not doc.is_label and doc.doc_type in scope.doc_types and _in_window(doc, scope.date_from, scope.date_to)
    ]
    required = {p for doc in in_scope for p in doc.page_ids}
    read = {p for c in claim.coverage_ids if coverage[c].mode is CoverageMode.READ for p in coverage[c].page_ids}
    reasons = []
    if all(coverage[c].mode is CoverageMode.SEARCH for c in claim.coverage_ids):
        reasons.append("backed only by searches; a negative needs the pages to have been read")
    uncovered = sorted(required - read)
    if uncovered:
        reasons.append(f"{len(uncovered)} page(s) in scope were never read")
    status = Status.REFUSED if reasons else Status.VERIFIED
    return Verdict(claim_id=claim.id, status=status, reasons=reasons, uncovered_page_ids=uncovered)
