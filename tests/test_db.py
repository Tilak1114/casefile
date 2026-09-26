import pytest

from casefile import db


@pytest.mark.integration
def test_local_mongo_ping():
    assert db.ping()


@pytest.mark.integration
def test_database_supports_search_indexes():
    """Local atlas-local and Atlas both accept search index commands; plain mongod does not."""
    collection = db.database()["_search_probe"]
    collection.drop()
    collection.insert_one({"text": "probe"})
    name = collection.create_search_index({"name": "probe", "definition": {"mappings": {"dynamic": True}}})
    assert name == "probe"
    collection.drop()


@pytest.mark.integration
def test_answer_key_quotes_exact_match_ingested_text():
    """Every evidence quote in the answer key must be findable in the stored text of its page."""
    import re

    import yaml

    from casefile.config import DATA_DIR
    from casefile.evaluation.answer_key import AnswerKey

    key = AnswerKey.model_validate(yaml.safe_load((DATA_DIR / "cases/HWY06MH024/answer_key.yaml").read_text()))
    pages = db.database().pages

    def ws(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    missing = []
    for item in [*key.events, *key.relationships, *key.parties]:
        for c in item.evidence:
            page = pages.find_one({"case_id": key.case_id, "file_no": c.file_no, "page": c.page})
            if page is None or page["is_label"] or ws(c.quote) not in ws(page["text"]):
                missing.append(f"{item.id} {c.file_no}:{c.page}")
    assert missing == []


@pytest.mark.integration
def test_every_answer_key_citation_passes_the_verifier():
    import yaml

    from casefile.config import DATA_DIR
    from casefile.evaluation.answer_key import AnswerKey
    from casefile.ingest.models import page_id
    from casefile.verify.load import load_index
    from casefile.verify.models import Citation, Claim, Status
    from casefile.verify.verifier import verify_claim

    key = AnswerKey.model_validate(yaml.safe_load((DATA_DIR / "cases/HWY06MH024/answer_key.yaml").read_text()))
    index = load_index(db.database(), key.case_id)
    refused = []
    for item in [*key.events, *key.relationships, *key.parties]:
        if not item.evidence:
            continue
        claim = Claim(
            id=item.id, statement=item.id,
            citations=[Citation(page_id=page_id(key.case_id, c.file_no, c.page), quote=c.quote) for c in item.evidence],
        )
        verdict = verify_claim(claim, index)
        if verdict.status is not Status.VERIFIED:
            refused.append((item.id, verdict.reasons))
    assert refused == []


@pytest.mark.integration
def test_negative_over_real_case_needs_every_letter_read():
    """Reading all letters but one leaves exactly that letter's pages uncovered."""
    from casefile.verify.coverage import CoverageLog
    from casefile.verify.load import load_index
    from casefile.verify.models import NegativeClaim, NegativeScope, Status
    from casefile.verify.verifier import verify_negative

    database = db.database()
    index = load_index(database, "HWY06MH024")
    letters = [d for d in index.documents.values() if d.doc_type == "letter" and not d.is_label]
    log = CoverageLog(database, "HWY06MH024", run_id="test-negative")
    try:
        skipped = letters[0]
        partial = log.read([p for d in letters[1:] for p in d.page_ids])
        claim = NegativeClaim(id="N", statement="no letter says X",
                              scope=NegativeScope(doc_types=["letter"]), coverage_ids=[partial.id])
        verdict = verify_negative(claim, index, log.records())
        assert verdict.status is Status.REFUSED
        assert verdict.uncovered_page_ids == sorted(skipped.page_ids)

        full = log.read(skipped.page_ids)
        claim = claim.model_copy(update={"coverage_ids": [partial.id, full.id]})
        assert verify_negative(claim, index, log.records()).status is Status.VERIFIED
    finally:
        database.coverage.delete_many({"run_id": "test-negative"})


@pytest.mark.integration
def test_search_finds_the_letter_and_never_returns_labels():
    from casefile import search

    hits = search.search_pages(db.database(), "HWY06MH024", "tensile movement anchors", limit=10)
    ids = [h["_id"] for h in hits]
    assert "HWY06MH024:040:p002" in ids[:3]  # the 7 Oct 1999 letter
    labels = {p["_id"] for p in db.database().pages.find({"is_label": True}, {"_id": 1})}
    assert not labels & set(ids)


@pytest.mark.integration
def test_mongo_event_store_is_append_only_ordered_and_watchable():
    import threading
    from uuid import uuid4

    from casefile.team.dispatcher import Dispatcher
    from casefile.team.events import Actor, EventType as E
    from casefile.team.store import MongoStore, TaskState

    database = db.database()
    run = f"test-{uuid4().hex[:8]}"
    store = MongoStore(database, run)
    d = Dispatcher(store, case_id="C", run_id=run, max_running=4)
    try:
        e = d.emit(E.COUNSEL_ASSIGNED, Actor.LEAD, to=Actor.COUNSEL, correlation_id="c1")
        assert d.publish(e) is None  # same id again: not appended twice
        assert [x.seq for x in store.events()] == [1]
        assert store.has_event(E.COUNSEL_ASSIGNED, "c1") and not store.has_event(E.COUNSEL_ASSIGNED, "c2")
        started = d.cycle()
        assert [t.role for t in started] == [Actor.COUNSEL]
        assert store.task(started[0].id).state is TaskState.RUNNING
        # a change stream wakes a waiting consumer when an event is appended
        threading.Timer(1.0, lambda: d.emit(E.WORK_ASSIGNED, Actor.LEAD, to=Actor.COUNSEL)).start()
        assert store.wait_for_new_events(timeout_s=15)
    finally:
        for c in ("events", "tasks"):
            database[c].delete_many({"run_id": run})
        database.counters.delete_one({"_id": f"events:{run}"})
