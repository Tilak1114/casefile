"""The team's one gate to the model: at most N calls at once across every agent, each call recorded."""

import threading
from datetime import UTC, datetime
from typing import Protocol, TypeVar

from pydantic import BaseModel
from pymongo.database import Database

from casefile.models.openrouter import ModelUsage

T = TypeVar("T", bound=BaseModel)
MAX_MODEL_CALLS_AT_ONCE = 4


class ModelClient(Protocol):
    model: str

    def structured(self, task: str, prompt: str, schema: type[T]) -> tuple[T, ModelUsage, bool]: ...


class ModelGate:
    def __init__(self, client: ModelClient, db: Database | None, run_id: str, max_at_once: int = MAX_MODEL_CALLS_AT_ONCE):
        self.client = client
        self.db = db
        self.run_id = run_id
        self._slots = threading.BoundedSemaphore(max_at_once)

    def call(self, *, actor: str, purpose: str, prompt: str, schema: type[T], task_id: str | None = None) -> tuple[T, ModelUsage]:
        with self._slots:
            output, usage, cached = self.client.structured(f"{actor}-{purpose}", prompt, schema)
        if self.db is not None:
            self.db.model_calls.insert_one({
                "run_id": self.run_id, "actor": actor, "purpose": purpose, "task_id": task_id, "model": self.client.model,
                "prompt_chars": len(prompt), "cached": cached, **usage.model_dump(), "at": datetime.now(UTC),
            })
        return output, usage

    def spent(self) -> dict:
        if self.db is None:
            return {}
        agg = list(self.db.model_calls.aggregate([
            {"$match": {"run_id": self.run_id}},
            {"$group": {"_id": None, "calls": {"$sum": 1}, "prompt": {"$sum": "$prompt_tokens"},
                        "output": {"$sum": "$output_tokens"}, "cost": {"$sum": "$cost_usd"}}},
        ]))
        return agg[0] if agg else {"calls": 0, "prompt": 0, "output": 0, "cost": 0.0}
