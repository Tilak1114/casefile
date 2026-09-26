"""Typed records for the harness: what workers return, what the examiner decides, what is stored."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from casefile.verify.models import PartialDate

# ---- what a reader returns (the Gemini response schema) ------------------------------------------


class QuoteRef(BaseModel):
    page_id: str = Field(description="Id of the page the quote is on, exactly as given.")
    quote: str = Field(description="Words copied character for character from that page, 5 to 40 words.")


class DateSource(StrEnum):
    DOCUMENT_DATE = "document_date"  # the event is the document itself being written or sent
    STATED_IN_TEXT = "stated_in_text"  # the text states when something happened


class EventClaim(BaseModel):
    date: str = Field(description="YYYY-MM-DD, or YYYY-MM or YYYY when the record is less precise.")
    date_source: DateSource = Field(
        description="document_date if the event is this document being issued; stated_in_text if the "
        "text says when it happened, in which case a quote must show that date."
    )
    statement: str = Field(description="What happened, in one plain sentence. No opinions about cause or fault.")
    quotes: list[QuoteRef] = Field(min_length=1)


class PartyMention(BaseModel):
    name: str = Field(description="The party's name exactly as written in the quote.")
    kind: Literal["organization", "person"]
    role: str = Field(description="Its role on the project as the record shows it, e.g. contractor, designer.")
    quotes: list[QuoteRef] = Field(min_length=1)


class RelationType(StrEnum):
    CONTRACTED_WITH = "contracted_with"
    DESIGNED_FOR = "designed_for"
    REPRESENTED = "represented"
    REVIEWED_SUBMITTALS_FOR = "reviewed_submittals_for"
    SUPPLIED = "supplied"
    SUBCONTRACTED_TO = "subcontracted_to"
    INSPECTED_FOR = "inspected_for"
    OVERSAW = "oversaw"


class RelationshipClaim(BaseModel):
    source: str = Field(description="First party, exactly as written in a quote.")
    type: RelationType
    target: str = Field(description="Second party, exactly as written in a quote.")
    quotes: list[QuoteRef] = Field(min_length=1)


class AliasClaim(BaseModel):
    name: str = Field(description="One way the record writes a party.")
    same_as: str = Field(description="Another way the record writes the same party.")
    quote: QuoteRef = Field(description="A quote that contains both names, showing they are the same party.")


class AbsenceClaim(BaseModel):
    statement: str = Field(description="Something the case file does not contain, stated plainly.")
    doc_types: list[str] = Field(min_length=1, description="Document types the absence applies to.")
    date_from: str | None = Field(None, description="Start of the window, YYYY[-MM[-DD]], if any.")
    date_to: str | None = Field(None, description="End of the window, YYYY[-MM[-DD]], if any.")
    search_terms: list[str] = Field(
        min_length=1,
        description="Short phrases that would appear on a page contradicting the absence. If a search "
        "finds any of them in scope, the absence is refused.",
    )


class NegativesOutput(BaseModel):
    absences: list[AbsenceClaim] = []


class ReaderOutput(BaseModel):
    events: list[EventClaim] = []
    parties: list[PartyMention] = []
    relationships: list[RelationshipClaim] = []
    aliases: list[AliasClaim] = []
    open_questions: list[str] = Field(
        [], description="References to documents or facts you could not find in what you read."
    )


# ---- roles and the examiner ------------------------------------------------------------------------


class Role(StrEnum):
    PARTIES = "parties_reviewer"  # v1
    TECHNICAL = "technical_reviewer"  # v1
    COUNSEL = "counsel"  # v2: defense counsel
    ENGINEER = "engineer"  # v2: forensic engineer


class Assign(BaseModel):
    action: Literal["assign"] = "assign"
    role: Role
    document_ids: list[str] = Field(min_length=1)
    focus: str = Field(description="What the role should look for in these documents.")


class SearchAction(BaseModel):
    action: Literal["search"] = "search"
    role: Role = Field(description="The role that will read what the search finds.")
    query: str
    reason: str = Field(description="The open question or gap this search follows up.")


class Repair(BaseModel):
    action: Literal["repair"] = "repair"
    refusal_ids: list[str] = Field(min_length=1)


class Finish(BaseModel):
    action: Literal["finish"] = "finish"
    reason: str


ExaminerAction = Annotated[Assign | SearchAction | Repair | Finish, Field(discriminator="action")]


class ExaminerDecision(BaseModel):
    """The Gemini response schema for the examiner: one action per turn."""

    thinking: str = Field(description="One or two sentences on why this is the next step.")
    assign: Assign | None = None
    search: SearchAction | None = None
    repair: Repair | None = None
    finish: Finish | None = None

    def action(self) -> Assign | SearchAction | Repair | Finish | None:
        chosen = [a for a in (self.assign, self.search, self.repair, self.finish) if a is not None]
        return chosen[0] if len(chosen) == 1 else None


# ---- stored records --------------------------------------------------------------------------------


class ClaimKind(StrEnum):
    EVENT = "event"
    PARTY = "party"
    RELATIONSHIP = "relationship"
    ALIAS = "alias"
    NEGATIVE = "negative"


class StoredClaim(BaseModel):
    """A claim after verification; lands in `findings` (verified) or `refusals` (refused)."""

    model_config = ConfigDict(frozen=True)

    id: str
    run_id: str
    case_id: str
    kind: ClaimKind
    role: Role
    worker_id: str
    statement: str
    date: PartialDate | None = None
    citations: list[QuoteRef] = []
    payload: EventClaim | PartyMention | RelationshipClaim | AliasClaim | AbsenceClaim
    verified: bool
    reasons: list[str] = []
    matches: list[dict[str, int | str]] = []  # page_id, start, end
    repair_of: str | None = None
    name_aliases: dict[str, str] = {}  # party name -> id of the verified alias claim that shows it in the quote
    created_at: datetime


class WorkerRecord(BaseModel):
    id: str
    run_id: str
    role: Role
    document_ids: list[str]
    page_ids: list[str]
    focus: str
    coverage_id: str
    verified: int
    refused: int
    open_questions: list[str]
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int
    cached: bool
    seconds: float


class TraceKind(StrEnum):
    RUN_START = "run_start"
    DECISION = "decision"
    REJECTED = "rejected"
    WORKER = "worker"
    SEARCH = "search"
    PROGRESS = "progress"
    ASSEMBLE = "assemble"
    RUN_END = "run_end"


class TraceEvent(BaseModel):
    run_id: str
    seq: int
    turn: int
    kind: TraceKind
    summary: str
    at: datetime
    action: Assign | SearchAction | Repair | Finish | None = None
    worker_ids: list[str] = []
    context_chars: int | None = None  # size of the examiner's prompt this turn
    coverage_pages: int | None = None  # readable pages read so far
    verified_total: int | None = None
    refused_total: int | None = None
    tokens: int | None = None


class RunState(BaseModel):
    """LangGraph state. Small on purpose: everything the run learns lives in MongoDB."""

    run_id: str
    case_id: str
    turn: int = 0
    spawns: int = 0
    unproductive: int = 0
    last_action: Assign | SearchAction | Repair | Finish | None = None
    last_rejection: str | None = None
    progress_marker: int = 0  # verified findings + pages read, at the end of the last turn
    done: bool = False
    stop_reason: str | None = None
