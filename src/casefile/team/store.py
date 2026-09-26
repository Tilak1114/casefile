"""Where events and tasks live: in memory for tests, in MongoDB for runs. Same interface."""

import threading
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field
from pymongo import ASCENDING, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from casefile.team.events import Actor, Event, EventType, WaitFor


class TaskState(StrEnum):
    PENDING = "pending"  # waiting for its waits_for
    READY = "ready"  # may start when a slot is free
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    EXPIRED = "expired"  # passed its deadline before it could start


class Task(BaseModel):
    id: str
    run_id: str
    role: Actor
    kind: str  # what the task is for, in words
    key: str  # idempotency key: one task per (role, trigger)
    trigger_event_id: str | None = None
    correlation_id: str | None = None
    waits_for: list[WaitFor] = []
    state: TaskState = TaskState.PENDING
    created_cycle: int
    deadline_cycle: int
    started_cycle: int | None = None
    note: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryStore:
    def __init__(self):
        self._events: list[Event] = []
        self._ids: set[str] = set()
        self._tasks: dict[str, Task] = {}
        self._keys: set[str] = set()
        self._lock = threading.Lock()

    def append(self, event: Event) -> Event | None:
        with self._lock:
            if event.id in self._ids:
                return None
            stored = event.model_copy(update={"seq": len(self._events) + 1})
            self._events.append(stored)
            self._ids.add(event.id)
            return stored

    def events(self, since_seq: int = 0) -> list[Event]:
        return [e for e in self._events if e.seq > since_seq]

    def has_event(self, type_: EventType, correlation_id: str | None) -> bool:
        return any(e.type is type_ and (correlation_id is None or e.correlation_id == correlation_id) for e in self._events)

    def add_task(self, task: Task) -> bool:
        with self._lock:
            if task.key in self._keys:
                return False
            self._keys.add(task.key)
            self._tasks[task.id] = task
            return True

    def task(self, task_id: str) -> Task:
        return self._tasks[task_id]

    def tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def save_task(self, task: Task) -> None:
        self._tasks[task.id] = task


class MongoStore:
    """Events and tasks in MongoDB. The events collection is append-only; `seq` gives the log a total order."""

    def __init__(self, db: Database, run_id: str):
        self.db = db
        self.run_id = run_id
        self.db.events.create_index([("run_id", ASCENDING), ("seq", ASCENDING)], unique=True)
        self.db.tasks.create_index([("run_id", ASCENDING), ("key", ASCENDING)], unique=True)

    def _next_seq(self) -> int:
        doc = self.db.counters.find_one_and_update({"_id": f"events:{self.run_id}"}, {"$inc": {"seq": 1}},
                                                   upsert=True, return_document=ReturnDocument.AFTER)
        return doc["seq"]

    def append(self, event: Event) -> Event | None:
        if self.db.events.count_documents({"_id": event.id}, limit=1):
            return None
        stored = event.model_copy(update={"seq": self._next_seq()})
        try:
            self.db.events.insert_one({"_id": stored.id, **stored.model_dump(mode="json")})
        except DuplicateKeyError:
            return None
        return stored

    def events(self, since_seq: int = 0) -> list[Event]:
        return [Event.model_validate(d) for d in self.db.events.find({"run_id": self.run_id, "seq": {"$gt": since_seq}}).sort("seq", 1)]

    def has_event(self, type_: EventType, correlation_id: str | None) -> bool:
        q = {"run_id": self.run_id, "type": type_.value}
        if correlation_id is not None:
            q["correlation_id"] = correlation_id
        return bool(self.db.events.count_documents(q, limit=1))

    def add_task(self, task: Task) -> bool:
        try:
            self.db.tasks.insert_one({"_id": task.id, **task.model_dump(mode="json")})
            return True
        except DuplicateKeyError:
            return False

    def task(self, task_id: str) -> Task:
        return Task.model_validate(self.db.tasks.find_one({"_id": task_id}))

    def tasks(self) -> list[Task]:
        return [Task.model_validate(d) for d in self.db.tasks.find({"run_id": self.run_id})]

    def save_task(self, task: Task) -> None:
        task = task.model_copy(update={"updated_at": datetime.now(UTC)})
        self.db.tasks.replace_one({"_id": task.id}, {"_id": task.id, **task.model_dump(mode="json")})

    def wait_for_new_events(self, timeout_s: float) -> bool:
        """Block on a change stream until an event is inserted for this run, or the timeout passes."""
        pipeline = [{"$match": {"operationType": "insert", "fullDocument.run_id": self.run_id}}]
        with self.db.events.watch(pipeline, max_await_time_ms=int(timeout_s * 1000)) as stream:
            return stream.try_next() is not None
