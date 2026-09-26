"""The run's memory in MongoDB: verified findings, refusals, pending negatives, workers and the trace."""

import threading
from datetime import UTC, datetime

from pymongo.database import Database

from casefile.harness.models import StoredClaim, TraceEvent, TraceKind, WorkerRecord


class RunStore:
    def __init__(self, db: Database, case_id: str, run_id: str):
        self.db = db
        self.case_id = case_id
        self.run_id = run_id
        self._seq_lock = threading.Lock()
        last = db.trace.find_one({"run_id": run_id}, sort=[("seq", -1)])
        self._seq = last["seq"] if last else 0

    def save_claims(self, claims: list[StoredClaim]) -> tuple[int, int]:
        verified = refused = 0
        for c in claims:
            doc = {"_id": c.id, **c.model_dump(mode="json")}
            if c.verified:
                target, verified = self.db.findings, verified + 1
            elif c.reasons and c.reasons[0].startswith("pending"):
                target = self.db.pending
            else:
                target, refused = self.db.refusals, refused + 1
            target.replace_one({"_id": c.id}, doc, upsert=True)
        return verified, refused

    def promote(self, claim: StoredClaim) -> None:
        """Move a claim that passed a later check (a repair, a negative) into findings."""
        self.db.pending.delete_one({"_id": claim.id})
        self.db.findings.replace_one({"_id": claim.id}, {"_id": claim.id, **claim.model_dump(mode="json")}, upsert=True)

    def refuse(self, claim: StoredClaim) -> None:
        self.db.pending.delete_one({"_id": claim.id})
        self.db.refusals.replace_one({"_id": claim.id}, {"_id": claim.id, **claim.model_dump(mode="json")}, upsert=True)

    def save_worker(self, worker: WorkerRecord) -> None:
        self.db.workers.replace_one({"_id": worker.id}, {"_id": worker.id, **worker.model_dump(mode="json")}, upsert=True)

    def trace(self, turn: int, kind: TraceKind, summary: str, **fields) -> TraceEvent:
        with self._seq_lock:
            self._seq += 1
            event = TraceEvent(run_id=self.run_id, seq=self._seq, turn=turn, kind=kind, summary=summary,
                               at=datetime.now(UTC), **fields)
        self.db.trace.insert_one(event.model_dump(mode="json"))
        return event

    def claims(self, collection: str) -> list[StoredClaim]:
        return [StoredClaim.model_validate(d) for d in self.db[collection].find({"run_id": self.run_id})]

    def count(self, collection: str) -> int:
        return self.db[collection].count_documents({"run_id": self.run_id})

    def pages_read(self) -> set[str]:
        return {p for r in self.db.coverage.find({"run_id": self.run_id, "mode": "read"}) for p in r["page_ids"]}
