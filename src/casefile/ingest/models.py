"""Typed records produced by ingestion."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class BBox(BaseModel):
    """Normalised box on a page (0-1, origin top-left), as Reducto returns it."""

    model_config = ConfigDict(frozen=True)

    left: float
    top: float
    width: float
    height: float
    page: int = Field(ge=1)


class ReductoBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    type: str
    content: str
    bbox: BBox
    confidence: str | None = None


class SplitPartition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    pages: list[int]
    conf: str


class SplitSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    pages: list[int]
    conf: str
    partitions: list[SplitPartition] | None = None


class BlockSpan(BaseModel):
    """Where one Reducto block's cleaned text sits in the page text."""

    model_config = ConfigDict(frozen=True)

    start: int
    end: int
    type: str
    bbox: BBox


class PageText(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    file_no: int
    page: int = Field(ge=1)
    text: str
    blocks: list[BlockSpan]
    stripped: dict[str, int]  # markup removed from Reducto output, by kind, with counts
    figures_dropped: int
    is_label: bool  # a production label: never shown to the agent, never citable

    @property
    def id(self) -> str:
        return page_id(self.case_id, self.file_no, self.page)


class SplitConfidence(StrEnum):
    HIGH = "high"
    LOW = "low"


class LogicalDocument(BaseModel):
    """One original document inside a file, as found by Reducto Split."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    file_no: int
    index: int = Field(ge=1)  # order within the file
    doc_type: str
    pages: list[int] = Field(min_length=1)
    split_label: str  # Split's model-written name for the partition; a hint, not evidence
    confidence: SplitConfidence

    @property
    def id(self) -> str:
        return f"{self.case_id}:{self.file_no:03d}:d{self.index:02d}"

    @property
    def is_label(self) -> bool:
        return self.doc_type == "production_label"


class FileIngest(BaseModel):
    case_id: str
    file_no: int
    sha256: str
    pages: int
    documents: int
    label_pages: int
    unassigned_pages: list[int]
    parse_credits: float
    split_credits: float
    cached: bool


class IngestRun(BaseModel):
    case_id: str
    started_at: datetime
    finished_at: datetime
    files: list[FileIngest]
    failures: list[str]


def page_id(case_id: str, file_no: int, page: int) -> str:
    return f"{case_id}:{file_no:03d}:p{page:03d}"
