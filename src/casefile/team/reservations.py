"""A role reserves a document before reading it, so concurrent tasks of the same role never read it twice."""

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError


def reserve(db: Database, run_id: str, role: str, document_ids: list[str], task_id: str) -> list[str]:
    """The subset of documents this task now holds; documents another task of the same role holds are skipped."""
    held = []
    for doc_id in document_ids:
        try:
            db.reservations.insert_one({"_id": f"{run_id}:{role}:{doc_id}", "run_id": run_id, "role": role,
                                        "document_id": doc_id, "task_id": task_id})
            held.append(doc_id)
        except DuplicateKeyError:
            continue
    return held
