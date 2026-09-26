"""The team's events: every interaction between roles is one of these, appended to the event log."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Actor(StrEnum):
    SYSTEM = "system"
    LEAD = "lead"
    COUNSEL = "counsel"
    ENGINEER = "engineer"
    VERIFIER = "verifier"
    DISPATCHER = "dispatcher"
    ASSEMBLY = "assembly"


class EventType(StrEnum):
    CLAIM_FILE_OPENED = "claim_file.opened"
    COUNSEL_ASSIGNED = "counsel.assigned"
    EXPERT_REQUESTED = "expert.requested"
    EXPERT_APPROVED = "expert.approved"
    EXPERT_DECLINED = "expert.declined"
    WORK_ASSIGNED = "work.assigned"
    READER_FINISHED = "reader.finished"
    CLAIM_VERIFIED = "claim.verified"
    CLAIM_REFUSED = "claim.refused"
    REQUEST_RAISED = "request.raised"
    REQUEST_ANSWERED = "request.answered"
    REPORT_SUBMITTED = "report.submitted"
    DISPUTE_OPENED = "dispute.opened"
    POSITION_SUBMITTED = "position.submitted"
    DISPUTE_RULED = "dispute.ruled"
    ABSENCE_PROPOSED = "absence.proposed"
    ABSENCE_CHECKED = "absence.checked"
    SCOPE_EXCLUDED = "scope.excluded"
    TASK_EXPIRED = "task.expired"
    GUARD_HIT = "guard.hit"
    CLAIM_FILE_CLOSED = "claim_file.closed"
    BRIEF_SUBMITTED = "brief.submitted"


class Event(BaseModel):
    """One entry in the append-only log. `payload` is validated per type by the role that reads it."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"ev-{uuid4().hex[:12]}")
    case_id: str
    run_id: str
    type: EventType
    sender: Actor
    to: Actor | None = None  # None: for everyone who subscribes to this type
    subject_ids: list[str] = []  # claims, documents or tasks it concerns
    correlation_id: str  # the conversation it belongs to (a request and its answer share one)
    causation_id: str | None = None  # the event that caused it
    payload: dict = {}
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    seq: int = 0  # position in the log, set on append


class WaitFor(BaseModel):
    """A task may start only once an event of this type exists in the same conversation (or any, if None)."""

    model_config = ConfigDict(frozen=True)

    type: EventType
    correlation_id: str | None = None
