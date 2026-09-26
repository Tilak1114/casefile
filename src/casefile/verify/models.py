"""Typed claims, coverage records and verification results."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

PartialDate = Annotated[str, Field(pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")]


class Citation(BaseModel):
    """A passage the claim relies on: a page and a verbatim quote from it."""

    model_config = ConfigDict(frozen=True)

    page_id: str
    quote: str = Field(min_length=1)


class AssertedFields(BaseModel):
    """Typed facts the claim states about the cited document; each is checked against its metadata."""

    model_config = ConfigDict(frozen=True)

    date: PartialDate | None = None
    author_org: str | None = None
    recipient_org: str | None = None
    doc_type: str | None = None


class Claim(BaseModel):
    """A positive statement: a chronology entry, a relationship, a finding."""

    model_config = ConfigDict(frozen=True)

    id: str
    statement: str
    citations: list[Citation] = []
    asserted: AssertedFields = AssertedFields()


class NegativeScope(BaseModel):
    """What a negative claim says is absent, and where: document types within a date window."""

    model_config = ConfigDict(frozen=True)

    doc_types: list[str] = Field(min_length=1)
    date_from: PartialDate | None = None
    date_to: PartialDate | None = None


class NegativeClaim(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    statement: str
    scope: NegativeScope
    coverage_ids: list[str] = Field(min_length=1)


class CoverageMode(StrEnum):
    READ = "read"  # the full page text was given to the model
    SEARCH = "search"  # a query ran over the pages; only the query terms were checked


class CoverageRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    run_id: str
    mode: CoverageMode
    page_ids: list[str]
    query: str | None = None
    actor: str | None = None  # who read or searched (a role, or a reader working for one)
    focus: str | None = None  # what they were reading for
    created_at: datetime


class Status(StrEnum):
    VERIFIED = "verified"
    REFUSED = "refused"
    INTERPRETATION = "interpretation"  # no citation: shown as the agent's reading, never as fact


class MatchedQuote(BaseModel):
    """Where a quote was found, as offsets into the stored page text (for highlighting)."""

    model_config = ConfigDict(frozen=True)

    page_id: str
    start: int
    end: int


class Verdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_id: str
    status: Status
    reasons: list[str] = []
    matches: list[MatchedQuote] = []
    uncovered_page_ids: list[str] = []  # for negatives: pages in scope that no read covered
