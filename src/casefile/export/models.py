"""The typed bundle the web UI reads. One per run; the TypeScript types are generated from this schema."""

from pydantic import BaseModel


class Box(BaseModel):
    left: float
    top: float
    width: float
    height: float


class Highlight(BaseModel):
    page_id: str
    quote: str
    boxes: list[Box]


class PageRef(BaseModel):
    page_id: str
    file_no: int
    page: int
    image: str | None  # path under /data, or None if not rendered
    is_label: bool


class DocumentRow(BaseModel):
    id: str
    file_no: int
    doc_type: str
    date: str | None
    author: str | None
    recipient: str | None
    page_ids: list[str]
    is_label: bool
    split_label: str
    split_confidence: str
    read_by: list[str]


class Claim(BaseModel):
    id: str
    kind: str
    role: str
    worker_id: str
    statement: str
    date: str | None
    verified: bool
    reasons: list[str]
    checks: list[str]
    highlights: list[Highlight]
    repair_of: str | None
    repair_attempted: bool = False
    detail: dict[str, str]  # kind-specific fields: party name/role, relationship ends, alias names


class ChronologyRow(BaseModel):
    date: str
    statement: str
    claim_ids: list[str]
    roles: list[str]
    document_id: str | None  # the document of the first quote
    lane: str  # party id of the document's author, or "other"


class Lane(BaseModel):
    id: str
    label: str
    events: int


class PartyRow(BaseModel):
    id: str
    names: list[str]
    kind: str
    roles: list[str]
    claim_ids: list[str]


class LinkRow(BaseModel):
    source: str
    type: str
    target: str
    claim_ids: list[str]


class ExhibitRow(BaseModel):
    document_id: str
    doc_type: str
    date: str | None
    file_no: int
    sha256: str
    cited_by: int


class Coverage(BaseModel):
    documents_total: int
    documents_read: int
    pages_total: int
    pages_read: int
    unread_documents: list[str]
    searched_only_pages: list[str]


class WithheldFile(BaseModel):
    file_no: int
    reason: str


class TraceRow(BaseModel):
    seq: int
    turn: int
    kind: str
    summary: str
    at: str
    action: dict | None
    worker_ids: list[str]
    context_chars: int | None
    coverage_pages: int | None
    verified_total: int | None
    refused_total: int | None
    tokens: int | None


class WorkerRow(BaseModel):
    id: str
    role: str
    document_ids: list[str]
    pages: int
    focus: str
    verified: int
    refused: int
    open_questions: list[str]
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int
    seconds: float


class RoleSpec(BaseModel):
    role: str
    title: str
    mirrors: str
    brief: str
    default_focus: str
    tools: list[str]
    sees: str


class HarnessSpec(BaseModel):
    examiner_actions: list[str]
    examiner_sees: list[str]
    roles: list[RoleSpec]
    guards: dict[str, int]
    verifier_rules: list[str]
    negative_rule: str
    memory_collections: dict[str, str]


class SplitScore(BaseModel):
    events_found: int
    events_total: int
    core_found: int
    core_total: int
    relationships_found: int
    relationships_total: int


class ScoreRow(BaseModel):
    run_id: str
    dev: SplitScore
    heldout: SplitScore
    parties_found: int
    parties_total: int
    verified_claims: int
    refused_claims: int
    pages_read: int
    readers: int
    prompt_tokens: int
    output_tokens: int
    cost_usd: float


class KeyEventRow(BaseModel):
    id: str
    date: str
    summary: str
    core: bool
    split: str
    ntsb_page: str
    ntsb_quote: str
    evidence_pages: list[str]
    found_by: list[str]  # claim ids in this run that match


class RunInfo(BaseModel):
    run_id: str
    status: str
    turns: int
    started_at: str | None
    ended_at: str | None


class CaseInfo(BaseModel):
    case_id: str
    title: str
    event_date: str
    event_summary: str
    source: str
    inputs: int
    withheld: list[WithheldFile]


class Bundle(BaseModel):
    case: CaseInfo
    run: RunInfo
    harness: HarnessSpec
    documents: list[DocumentRow]
    pages: dict[str, PageRef]
    claims: list[Claim]
    refusals: list[Claim]
    chronology: list[ChronologyRow]
    lanes: list[Lane]
    parties: list[PartyRow]
    links: list[LinkRow]
    exhibits: list[ExhibitRow]
    negatives: list[str]
    coverage: Coverage
    trace: list[TraceRow]
    workers: list[WorkerRow]
    score: ScoreRow | None
    baseline: ScoreRow | None
    answer_key: list[KeyEventRow]
