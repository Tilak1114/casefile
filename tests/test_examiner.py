from unittest.mock import MagicMock

from casefile.harness.examiner import Deps, batches, validate
from casefile.harness.models import Assign, Finish, Role, RunState
from casefile.verify.index import CaseIndex, IndexedDocument, IndexedPage


def doc(i: int, pages: int, label: bool = False) -> IndexedDocument:
    return IndexedDocument(id=f"C:{i:03d}:d01", doc_type="production_label" if label else "letter",
                           page_ids=[f"C:{i:03d}:p{p:03d}" for p in range(1, pages + 1)], is_label=label)


def index(*docs: IndexedDocument) -> CaseIndex:
    pages = {p: IndexedPage(id=p, file_no=int(d.id[2:5]), page=int(p[-3:]), text="x", is_label=d.is_label, document_id=d.id)
             for d in docs for p in d.page_ids}
    return CaseIndex(case_id="C", pages=pages, documents={d.id: d for d in docs})


def deps_with(idx: CaseIndex, read_docs: list[str] = ()) -> Deps:
    store = MagicMock()
    store.run_id = "r"
    store.db.workers.find.return_value = [{"role": "technical_reviewer", "document_ids": list(read_docs)}]
    return Deps(gemini=MagicMock(), index=idx, store=store, coverage=MagicMock())


def test_batches_keep_documents_whole_and_bound_pages():
    groups = batches([doc(1, 10), doc(2, 10), doc(3, 10), doc(4, 40), doc(5, 3)], pages_per_reader=25)
    assert [[d.id[2:5] for d in g] for g in groups] == [["001", "002"], ["003"], ["004"], ["005"]]


def test_assign_rejects_labels_and_unknown_documents():
    idx = index(doc(1, 2), doc(2, 1, label=True))
    state = RunState(run_id="r", case_id="C")
    ok = Assign(role=Role.TECHNICAL, document_ids=["C:001:d01"], focus="dates")
    assert validate(ok, deps_with(idx), state) is None
    bad = Assign(role=Role.TECHNICAL, document_ids=["C:002:d01", "C:999:d01"], focus="dates")
    assert "not readable" in validate(bad, deps_with(idx), state)


def test_finish_is_rejected_while_documents_are_unread():
    idx = index(doc(1, 2), doc(2, 2))
    state = RunState(run_id="r", case_id="C")
    assert "1 documents have not been read" in validate(Finish(reason="done"), deps_with(idx, ["C:001:d01"]), state)
    assert validate(Finish(reason="done"), deps_with(idx, ["C:001:d01", "C:002:d01"]), state) is None


def test_no_action_or_several_actions_is_rejected():
    assert validate(None, deps_with(index(doc(1, 1))), RunState(run_id="r", case_id="C")) == "choose exactly one action"
