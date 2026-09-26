"""Atlas Search over page text: the index definition and the query the agent's search tool uses."""

import time

from pymongo.database import Database
from pymongo.operations import SearchIndexModel

PAGES_INDEX = "pages_text"
PAGES_DEFINITION = {
    "mappings": {
        "dynamic": False,
        "fields": {
            "text": {"type": "string", "analyzer": "lucene.english"},
            "case_id": {"type": "token"},
            "is_label": {"type": "boolean"},
            "file_no": {"type": "number"},
        },
    }
}


def ensure_indexes(db: Database, wait_seconds: int = 180) -> str:
    """Create or update the page search index and wait until it can be queried."""
    existing = {i["name"]: i for i in db.pages.list_search_indexes()}
    if PAGES_INDEX in existing:
        db.pages.update_search_index(PAGES_INDEX, PAGES_DEFINITION)
    else:
        db.pages.create_search_index(SearchIndexModel(definition=PAGES_DEFINITION, name=PAGES_INDEX))
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        status = next(iter(db.pages.list_search_indexes(PAGES_INDEX)), {})
        if status.get("queryable"):
            return status.get("status", "READY")
        time.sleep(3)
    raise TimeoutError(f"search index {PAGES_INDEX} not queryable after {wait_seconds}s")


def search_pages(db: Database, case_id: str, query: str, limit: int = 10, phrase: bool = False) -> list[dict]:
    """Readable, non-label pages matching the query, best first. Labels are never returned.

    With `phrase`, the words must appear together in order (used to look for counter-examples)."""
    operator = {"phrase": {"query": query, "path": "text"}} if phrase else {"text": {"query": query, "path": "text"}}
    pipeline = [
        {
            "$search": {
                "index": PAGES_INDEX,
                "compound": {
                    "must": [operator],
                    "filter": [
                        {"equals": {"path": "case_id", "value": case_id}},
                        {"equals": {"path": "is_label", "value": False}},
                    ],
                },
                "highlight": {"path": "text"},
            }
        },
        {"$limit": limit},
        {"$project": {"_id": 1, "file_no": 1, "page": 1, "score": {"$meta": "searchScore"},
                      "highlights": {"$meta": "searchHighlights"}}},
    ]
    return list(db.pages.aggregate(pipeline))
