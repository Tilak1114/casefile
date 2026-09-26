"""Coverage records: which pages a run actually read or searched. Negatives must cite them."""

from datetime import UTC, datetime
from uuid import uuid4

from pymongo.database import Database

from casefile.verify.models import CoverageMode, CoverageRecord


class CoverageLog:
    def __init__(self, db: Database, case_id: str, run_id: str):
        self.collection = db.coverage
        self.case_id = case_id
        self.run_id = run_id

    def _add(self, mode: CoverageMode, page_ids: list[str], query: str | None) -> CoverageRecord:
        record = CoverageRecord(
            id=f"cov-{uuid4().hex[:12]}", run_id=self.run_id, mode=mode,
            page_ids=sorted(set(page_ids)), query=query, created_at=datetime.now(UTC),
        )
        self.collection.insert_one({"_id": record.id, "case_id": self.case_id, **record.model_dump(mode="json")})
        return record

    def read(self, page_ids: list[str]) -> CoverageRecord:
        return self._add(CoverageMode.READ, page_ids, None)

    def search(self, page_ids: list[str], query: str) -> CoverageRecord:
        return self._add(CoverageMode.SEARCH, page_ids, query)

    def records(self) -> dict[str, CoverageRecord]:
        return {
            r["_id"]: CoverageRecord.model_validate(r)
            for r in self.collection.find({"case_id": self.case_id, "run_id": self.run_id})
        }
