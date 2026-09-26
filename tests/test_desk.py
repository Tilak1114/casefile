from unittest.mock import MagicMock

import pytest

from casefile.team import desk as desk_mod
from casefile.team.desk import DocumentQuery, RecordsDesk
from casefile.verify.index import CaseIndex, DocumentMetadata, IndexedDocument, IndexedPage, MetadataField
from casefile.verify.models import CoverageMode, CoverageRecord


def doc(i, text, doc_type="letter", date=None, author=None, label=False):
    pid = f"C:{i:03d}:p001"
    meta = DocumentMetadata(
        date=MetadataField(value=date, span=date, page_id=pid) if date else None,
        author_org=MetadataField(value=author, span=author, page_id=pid) if author else None,
    )
    d = IndexedDocument(id=f"C:{i:03d}:d01", doc_type=doc_type, page_ids=[pid], is_label=label, metadata=meta)
    p = IndexedPage(id=pid, file_no=i, page=1, text=text, is_label=label, document_id=d.id)
    return d, p


class FakeCoverage:
    def __init__(self):
        self.recs: dict[str, CoverageRecord] = {}

    def _add(self, mode, pages, query=None, actor=None, focus=None):
        from datetime import UTC, datetime
        r = CoverageRecord(id=f"k{len(self.recs)}", run_id="r", mode=mode, page_ids=pages, query=query, actor=actor, focus=focus, created_at=datetime.now(UTC))
        self.recs[r.id] = r
        return r

    def read(self, pages, actor=None, focus=None):
        return self._add(CoverageMode.READ, pages, None, actor, focus)

    def search(self, pages, query, actor=None):
        return self._add(CoverageMode.SEARCH, pages, query, actor)

    def records(self):
        return self.recs


@pytest.fixture
def desk():
    parts = [
        doc(1, "Letter No. C09B2-0350 re anchors. Contract C09B2", date="1999-10-12", author="Bechtel/Parsons Brinckerhoff"),
        doc(2, "In response to B/PB Letter No. C09B2-0350 we will retest. Contract C09B2", date="1999-11-08", author="Modern Continental"),
        doc(3, "Submittal 723.480-014 C returned. Contract C09B2", doc_type="submittal_transmittal", date="2000-01-07"),
        doc(4, "ATTACHMENT 9 - LETTER C09B2-0350", doc_type="production_label", label=True),
    ]
    index = CaseIndex(case_id="C", pages={p.id: p for _, p in parts}, documents={d.id: d for d, _ in parts})
    return RecordsDesk(MagicMock(), index, FakeCoverage())


def test_list_documents_filters_and_hides_labels(desk):
    ids = [r.id for r in desk.list_documents(DocumentQuery())]
    assert ids == ["C:001:d01", "C:002:d01", "C:003:d01"]
    assert [r.id for r in desk.list_documents(DocumentQuery(doc_types=["submittal_transmittal"]))] == ["C:003:d01"]
    assert [r.id for r in desk.list_documents(DocumentQuery(date_from="1999-11", date_to="1999-12"))] == ["C:002:d01"]
    assert [r.id for r in desk.list_documents(DocumentQuery(author="modern"))] == ["C:002:d01"]


def test_get_document_logs_who_read_it_and_why(desk):
    text = desk.get_document("C:002:d01", actor="engineer", focus="retesting")
    assert "retest" in text.pages[0].text
    row = desk.coverage_status(["C:002:d01"])[0]
    assert row.read_by == ["engineer"] and row.focuses == ["retesting"]
    with pytest.raises(KeyError):
        desk.get_document("C:004:d01", actor="engineer", focus="x")  # a production label is never readable


def test_find_references_links_documents_that_share_a_specific_code(desk):
    refs = {r.code: r.documents for r in desk.find_references("C:002:d01")}
    assert refs.get("C09B2-0350") == ["C:001:d01"]  # the letter it answers; the label is not a document to follow
    assert "C09B2" not in refs  # too short to be a specific reference


def test_codes_on_too_many_documents_are_ignored(desk, monkeypatch):
    monkeypatch.setattr(desk_mod, "MAX_DOCS_FOR_A_REFERENCE", 1)
    assert desk.find_references("C:002:d01") == []
