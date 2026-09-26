"""Fixes from smoke-2: attached references are not read twice, and the lead can retain the engineer itself."""

from types import SimpleNamespace

from casefile.team.desk import Reference
from casefile.team.dispatcher import Dispatcher, TaskState
from casefile.team.events import Actor, EventType as E
from casefile.team.lead import Retention, retain
from casefile.team.reader import MAX_ATTACHED_PAGES, _attach
from casefile.team.store import MemoryStore


def doc(id_, pages=3, label=False):
    return SimpleNamespace(id=id_, page_ids=[f"{id_}:p{i}" for i in range(pages)], is_label=label)


def index(*docs):
    return SimpleNamespace(documents={d.id: d for d in docs})


class Desk:
    def __init__(self, refs):
        self.refs = refs

    def find_references(self, doc_id):
        return [Reference(code="C09B2-1", documents=self.refs.get(doc_id, []))]


class Reservations:
    """Stands in for reserve(): a document can be held by one reader of the role, once."""

    def __init__(self, taken=()):
        self.taken = set(taken)

    def claim(self, ids):
        held = [i for i in ids if i not in self.taken]
        self.taken |= set(held)
        return held


def test_attaches_only_short_unreserved_documents_outside_the_batch():
    a, b = doc("a"), doc("b")
    idx = index(a, b, doc("long", MAX_ATTACHED_PAGES + 1), doc("label", label=True), doc("taken"), doc("ok"))
    desk = Desk({"a": ["b", "long", "label", "taken", "ok", "missing"]})
    assert _attach(desk, idx, [a, b], Reservations(taken={"taken"}).claim) == ["ok"]


def test_two_readers_citing_the_same_document_attach_it_once():
    idx = index(doc("a"), doc("b"), doc("shared"))
    desk = Desk({"a": ["shared"], "b": ["shared"]})
    r = Reservations()
    first = _attach(desk, idx, [idx.documents["a"]], r.claim)
    second = _attach(desk, idx, [idx.documents["b"]], r.claim)
    assert first == ["shared"] and second == []


def test_at_most_two_attachments():
    idx = index(doc("a"), doc("x"), doc("y"), doc("z"))
    r = Reservations()
    assert _attach(Desk({"a": ["x", "y", "z"]}), idx, [idx.documents["a"]], r.claim) == ["x", "y"]
    assert "z" not in r.taken  # not reserved, so another reader can still take it


def cause(d):
    return d.emit(E.CLAIM_FILE_OPENED, Actor.SYSTEM, to=Actor.LEAD)


def test_lead_retains_engineer_on_its_own_initiative_once():
    d = Dispatcher(MemoryStore(), case_id="C", run_id="r", max_running=4)
    idx = index(doc("t1"), doc("cover", label=True))
    c = cause(d)
    assert retain(d, idx, Retention(reason="lab reports", focus="anchor tests", document_ids=["t1", "cover", "nope"]), c)
    approvals = [e for e in d.store.events() if e.type is E.EXPERT_APPROVED]
    assert len(approvals) == 1 and approvals[0].payload["document_ids"] == ["t1"] and approvals[0].to is Actor.ENGINEER
    assert not retain(d, idx, Retention(reason="again", focus="x"), c)
    assert not retain(d, idx, None, c)


def test_engineer_work_after_retention_runs():
    d = Dispatcher(MemoryStore(), case_id="C", run_id="r", max_running=4)
    c = cause(d)
    retain(d, index(doc("t1")), Retention(reason="r", focus="f", document_ids=["t1"]), c)
    d.emit(E.WORK_ASSIGNED, Actor.LEAD, to=Actor.ENGINEER, payload={"document_ids": ["t1"], "focus": "f"})
    d.cycle()
    engineer = [t for t in d.store.tasks() if t.role is Actor.ENGINEER]
    assert len(engineer) == 2 and all(t.state is TaskState.RUNNING for t in engineer)


def test_the_lead_cannot_exclude_documents():
    from casefile.team.lead import NextStep, Opening
    from casefile.team.spec import SPECS

    assert "exclusions" not in Opening.model_fields and "exclusions" not in NextStep.model_fields
    assert E.SCOPE_EXCLUDED not in SPECS[Actor.LEAD].publishes
