import pytest

from casefile import db


@pytest.mark.integration
def test_local_mongo_ping():
    assert db.ping()


@pytest.mark.integration
def test_local_mongo_supports_search_indexes():
    """The atlas-local image must accept search index commands; plain mongod does not."""
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
