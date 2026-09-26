"""The verifier decides whether the demo holds up, so it is tested before anything uses it."""

from datetime import UTC, datetime

import pytest

from casefile.verify.index import CaseIndex, DocumentMetadata, IndexedDocument, IndexedPage, MetadataField
from casefile.verify.models import (
    AssertedFields,
    Citation,
    Claim,
    CoverageMode,
    CoverageRecord,
    NegativeClaim,
    NegativeScope,
    Status,
)
from casefile.verify.text import find_quote
from casefile.verify.verifier import verify_claim, verify_negative

LETTER = (
    "Modern Continental Construction Co., Inc.\n"
    "October 7, 1999\n"
    "a small percentage of the adhesive anchors in the HOV ceiling mockup appear to show signs of "
    "tensile movement. MCC’s position – as stated – is unchanged."
)


def meta(date=None, author=None, page="C:040:p002"):
    return DocumentMetadata(
        date=MetadataField(value=date, span="October 7, 1999", page_id=page) if date else None,
        author_org=MetadataField(value=author, span=author, page_id=page) if author else None,
    )


@pytest.fixture
def index() -> CaseIndex:
    pages = {
        "C:040:p001": IndexedPage(id="C:040:p001", file_no=40, page=1, text="ATTACHMENT 9 – LETTER FROM MODERN CONTINENTAL", is_label=True, document_id="C:040:d01"),
        "C:040:p002": IndexedPage(id="C:040:p002", file_no=40, page=2, text=LETTER, is_label=False, document_id="C:040:d02"),
        "C:041:p002": IndexedPage(id="C:041:p002", file_no=41, page=2, text="We have reviewed your letter.", is_label=False, document_id="C:041:d02"),
        "C:042:p002": IndexedPage(id="C:042:p002", file_no=42, page=2, text="Transmittal 723.480-014 C", is_label=False, document_id="C:042:d02"),
        "C:043:p002": IndexedPage(id="C:043:p002", file_no=43, page=2, text="An undated note.", is_label=False, document_id="C:043:d02"),
    }
    documents = {
        "C:040:d01": IndexedDocument(id="C:040:d01", doc_type="production_label", page_ids=["C:040:p001"], is_label=True),
        "C:040:d02": IndexedDocument(id="C:040:d02", doc_type="letter", page_ids=["C:040:p002"], is_label=False,
                                     metadata=meta(date="1999-10-07", author="Modern Continental Construction Co., Inc.")),
        "C:041:d02": IndexedDocument(id="C:041:d02", doc_type="letter", page_ids=["C:041:p002"], is_label=False,
                                     metadata=meta(date="1999-10-12", page="C:041:p002")),
        "C:042:d02": IndexedDocument(id="C:042:d02", doc_type="submittal_transmittal", page_ids=["C:042:p002"], is_label=False,
                                     metadata=meta(date="2000-01-07", page="C:042:p002")),
        "C:043:d02": IndexedDocument(id="C:043:d02", doc_type="letter", page_ids=["C:043:p002"], is_label=False),
    }
    return CaseIndex(case_id="C", pages=pages, documents=documents)


def claim(*citations, **asserted) -> Claim:
    return Claim(id="E1", statement="MCC reports anchor movement",
                 citations=[Citation(page_id=p, quote=q) for p, q in citations],
                 asserted=AssertedFields(**asserted))


def coverage(cid, pages, mode=CoverageMode.READ):
    return CoverageRecord(id=cid, run_id="r1", mode=mode, page_ids=pages, created_at=datetime.now(UTC))


# --- quote matching -------------------------------------------------------------------------------

def test_find_quote_collapses_whitespace_and_returns_original_offsets():
    text = "appear to show\n  signs of tensile movement"
    start, end = find_quote(text, "show signs of tensile")
    assert text[start:end] == "show\n  signs of tensile"


def test_find_quote_folds_curly_quotes_and_dashes_only_for_comparison():
    start, end = find_quote(LETTER, "MCC's position - as stated")
    assert LETTER[start:end] == "MCC’s position – as stated"


def test_find_quote_is_case_sensitive_and_exact_on_words():
    assert find_quote(LETTER, "tensile movements") is None
    assert find_quote(LETTER, "TENSILE movement") is None


# --- positive claims ------------------------------------------------------------------------------

def test_real_quote_verifies_with_highlight_offsets(index):
    verdict = verify_claim(claim(("C:040:p002", "appear to show signs of tensile movement")), index)
    assert verdict.status is Status.VERIFIED
    m = verdict.matches[0]
    assert LETTER[m.start : m.end] == "appear to show signs of tensile movement"


def test_altered_quote_is_refused(index):
    verdict = verify_claim(claim(("C:040:p002", "appear to show signs of tensile failure")), index)
    assert verdict.status is Status.REFUSED
    assert "not found" in verdict.reasons[0]


def test_quote_from_a_production_label_is_refused(index):
    verdict = verify_claim(claim(("C:040:p001", "LETTER FROM MODERN CONTINENTAL")), index)
    assert verdict.status is Status.REFUSED
    assert "production label" in verdict.reasons[0]


def test_quote_from_an_unknown_or_withheld_page_is_refused(index):
    verdict = verify_claim(claim(("C:092:p010", "anything")), index)
    assert verdict.status is Status.REFUSED
    assert "not a readable page" in verdict.reasons[0]


def test_one_bad_citation_refuses_the_whole_claim(index):
    verdict = verify_claim(
        claim(("C:040:p002", "tensile movement"), ("C:041:p002", "We rejected your letter.")), index
    )
    assert verdict.status is Status.REFUSED


def test_uncited_claim_is_interpretation_not_fact(index):
    verdict = verify_claim(Claim(id="E2", statement="The contractor was probably worried"), index)
    assert verdict.status is Status.INTERPRETATION


def test_asserted_date_must_match_document_metadata(index):
    ok = verify_claim(claim(("C:040:p002", "tensile movement"), date="1999-10-07"), index)
    assert ok.status is Status.VERIFIED
    coarser = verify_claim(claim(("C:040:p002", "tensile movement"), date="1999-10"), index)
    assert coarser.status is Status.VERIFIED
    wrong = verify_claim(claim(("C:040:p002", "tensile movement"), date="1999-11-07"), index)
    assert wrong.status is Status.REFUSED
    assert "date" in wrong.reasons[0]


def test_asserted_field_without_metadata_is_refused(index):
    verdict = verify_claim(claim(("C:043:p002", "An undated note"), date="1999-10-07"), index)
    assert verdict.status is Status.REFUSED
    assert "no date" in verdict.reasons[0]


def test_asserted_author_and_type(index):
    ok = verify_claim(claim(("C:040:p002", "tensile movement"), author_org="Modern Continental", doc_type="letter"), index)
    assert ok.status is Status.VERIFIED
    wrong = verify_claim(claim(("C:040:p002", "tensile movement"), doc_type="memorandum"), index)
    assert wrong.status is Status.REFUSED


# --- negatives ------------------------------------------------------------------------------------

def negative(*coverage_ids, doc_types=("letter",), date_from=None, date_to=None):
    return NegativeClaim(id="N1", statement="No letter approves the change",
                         scope=NegativeScope(doc_types=list(doc_types), date_from=date_from, date_to=date_to),
                         coverage_ids=list(coverage_ids))


def test_negative_with_full_read_coverage_verifies(index):
    records = {"k1": coverage("k1", ["C:040:p002", "C:041:p002", "C:043:p002"])}
    verdict = verify_negative(negative("k1"), index, records)
    assert verdict.status is Status.VERIFIED


def test_negative_with_a_gap_is_refused_and_names_the_gap(index):
    records = {"k1": coverage("k1", ["C:040:p002"])}
    verdict = verify_negative(negative("k1"), index, records)
    assert verdict.status is Status.REFUSED
    assert verdict.uncovered_page_ids == ["C:041:p002", "C:043:p002"]


def test_negative_date_window_still_requires_undated_documents(index):
    # Only the October 1999 letters are dated inside the window, but the undated letter might be too.
    records = {"k1": coverage("k1", ["C:040:p002", "C:041:p002"])}
    verdict = verify_negative(negative("k1", date_from="1999-10-01", date_to="1999-10-31"), index, records)
    assert verdict.uncovered_page_ids == ["C:043:p002"]


def test_negative_date_window_excludes_documents_dated_outside_it(index):
    records = {"k1": coverage("k1", ["C:040:p002", "C:041:p002", "C:043:p002"])}
    verdict = verify_negative(
        negative("k1", doc_types=("letter", "submittal_transmittal"), date_from="1999-10-01", date_to="1999-12-31"),
        index, records,
    )
    assert verdict.status is Status.VERIFIED  # the January 2000 transmittal is outside the window


def test_negative_backed_only_by_search_is_refused(index):
    records = {"k1": coverage("k1", ["C:040:p002", "C:041:p002", "C:043:p002"], mode=CoverageMode.SEARCH)}
    verdict = verify_negative(negative("k1"), index, records)
    assert verdict.status is Status.REFUSED


def test_negative_citing_unknown_coverage_is_refused(index):
    verdict = verify_negative(negative("missing"), index, {})
    assert verdict.status is Status.REFUSED
    assert "unknown coverage" in verdict.reasons[0]
