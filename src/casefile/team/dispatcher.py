"""The dispatcher: deterministic code that turns events into tasks and decides what may run.

It enforces the team's rules: a role may publish only its own events; a task starts only when its
`waits_for` events exist; a dependency no role can publish is refused when the task is created; no more
than `max_running` tasks run at once; a task still waiting at its deadline expires and the lead is told.
Delivery is at least once and handling is idempotent: an event id is appended once, and each role gets at
most one task per triggering event.
"""

from uuid import uuid4

from casefile.team.events import Actor, Event, EventType, WaitFor
from casefile.team.spec import MODEL_ROLES, SPECS, publishable
from casefile.team.store import MemoryStore, MongoStore, Task, TaskState


class NotAllowed(RuntimeError):
    pass


class Dispatcher:
    def __init__(self, store: MemoryStore | MongoStore, *, case_id: str, run_id: str, max_running: int = 4,
                 deadline_cycles: int = 12):
        self.store = store
        self.case_id = case_id
        self.run_id = run_id
        self.max_running = max_running
        self.deadline_cycles = deadline_cycles
        self.cycle_no = 0
        self._cursor = 0  # last event seq turned into tasks

    # ---- publishing -------------------------------------------------------------------------------

    def publish(self, event: Event) -> Event | None:
        """Append an event if its sender may publish it. Returns None if the id was already appended."""
        if event.type not in SPECS[event.sender].publishes:
            raise NotAllowed(f"{event.sender.value} may not publish {event.type.value}")
        return self.store.append(event)

    def emit(self, type_: EventType, sender: Actor, *, to: Actor | None = None, correlation_id: str | None = None,
             causation_id: str | None = None, subject_ids: list[str] | None = None, payload: dict | None = None) -> Event | None:
        return self.publish(Event(case_id=self.case_id, run_id=self.run_id, type=type_, sender=sender, to=to,
                                  correlation_id=correlation_id or f"c-{uuid4().hex[:10]}", causation_id=causation_id,
                                  subject_ids=subject_ids or [], payload=payload or {}))

    # ---- tasks ------------------------------------------------------------------------------------

    def create_task(self, role: Actor, kind: str, *, waits_for: list[WaitFor] | None = None,
                    trigger: Event | None = None) -> Task:
        for w in waits_for or []:
            if not publishable(w.type):
                raise NotAllowed(f"no role publishes {w.type.value}; this task could never start")
        key = f"{role.value}:{trigger.id}" if trigger else f"{role.value}:{kind}:{uuid4().hex[:8]}"
        task = Task(id=f"t-{uuid4().hex[:10]}", run_id=self.run_id, role=role, kind=kind, key=key,
                    trigger_event_id=trigger.id if trigger else None,
                    correlation_id=trigger.correlation_id if trigger else None, waits_for=waits_for or [],
                    created_cycle=self.cycle_no, deadline_cycle=self.cycle_no + self.deadline_cycles)
        if not self.store.add_task(task):
            return next(t for t in self.store.tasks() if t.key == key)
        return task

    def _consume(self) -> None:
        for event in self.store.events(since_seq=self._cursor):
            for role in MODEL_ROLES:
                if event.type in SPECS[role].wakes_on and event.to in (role, None) and event.sender is not role:
                    self.create_task(role, f"handle {event.type.value}", trigger=event)
            self._cursor = max(self._cursor, event.seq)

    def _satisfied(self, task: Task) -> bool:
        return all(self.store.has_event(w.type, w.correlation_id) for w in task.waits_for)

    def cycle(self) -> list[Task]:
        """One dispatcher cycle. Returns the tasks started in it."""
        self.cycle_no += 1
        for _ in range(10):  # expiries publish events that wake the lead; settle them within the cycle
            before = self._cursor
            self._consume()
            for task in self.store.tasks():
                if task.state is not TaskState.PENDING:
                    continue
                if self._satisfied(task):
                    self.store.save_task(task.model_copy(update={"state": TaskState.READY}))
                elif self.cycle_no > task.deadline_cycle:
                    self.store.save_task(task.model_copy(update={"state": TaskState.EXPIRED}))
                    self.emit(EventType.TASK_EXPIRED, Actor.DISPATCHER, to=Actor.LEAD, subject_ids=[task.id],
                              correlation_id=task.correlation_id, payload={"role": task.role.value, "kind": task.kind})
            if not self.store.events(since_seq=self._cursor) and self._cursor == before:
                break
        running = sum(t.state is TaskState.RUNNING for t in self.store.tasks())
        started = []
        for task in sorted((t for t in self.store.tasks() if t.state is TaskState.READY), key=lambda t: t.created_cycle):
            if running >= self.max_running:
                break
            task = task.model_copy(update={"state": TaskState.RUNNING, "started_cycle": self.cycle_no})
            self.store.save_task(task)
            started.append(task)
            running += 1
        return started

    def finish(self, task_id: str, note: str | None = None) -> None:
        self.store.save_task(self.store.task(task_id).model_copy(update={"state": TaskState.DONE, "note": note}))

    def fail(self, task_id: str, note: str) -> None:
        self.store.save_task(self.store.task(task_id).model_copy(update={"state": TaskState.FAILED, "note": note}))

    def open_work(self) -> list[Task]:
        return [t for t in self.store.tasks() if t.state in (TaskState.PENDING, TaskState.READY, TaskState.RUNNING)]


__all__ = ["Dispatcher", "NotAllowed", "TaskState"]
