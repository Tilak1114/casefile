"""The answer key: what a correct reconstruction must contain, traceable to the NTSB report.

Every item cites the case documents that show it (which the agent can read) and the page of the
NTSB report that establishes it (which the agent never sees).
"""

import re
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from casefile.docket.case import CaseConfig

ItemId = Annotated[str, Field(pattern=r"^[EPRN]\d{2,3}$")]
# A date as precise as the record allows: 1999, 1999-10 or 1999-10-07.
PartialDate = Annotated[str, Field(pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")]


class Split(StrEnum):
    DEV = "dev"  # used while building
    HELDOUT = "heldout"  # scored only at the end


class Status(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"


class NtsbRef(BaseModel):
    """Where the NTSB report HAR-07/02 establishes the item."""

    model_config = ConfigDict(frozen=True)

    page: str = Field(pattern=r"^(\d+|[ivxlc]+)$")  # printed page in HAR-07/02: "36" or "vii"
    quote: str = Field(min_length=10)


class Citation(BaseModel):
    """A passage in a case document the agent can read."""

    model_config = ConfigDict(frozen=True)

    file_no: int = Field(ge=1)
    page: int = Field(ge=1)  # 1-based page within the file
    quote: str = Field(min_length=8)


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: ItemId
    date: PartialDate
    date_end: PartialDate | None = None  # for events spanning several days
    summary: str
    evidence: list[Citation] = Field(min_length=1)
    ntsb: NtsbRef
    split: Split
    core: bool  # part of the causal chain, not background


class Negative(BaseModel):
    """Something the record does not contain, which a correct run must report as absent."""

    model_config = ConfigDict(frozen=True)

    id: ItemId
    statement: str
    must_have_read: list[int] = Field(min_length=1)  # files whose coverage the negative relies on
    ntsb: NtsbRef
    split: Split


class PartyKind(StrEnum):
    ORGANIZATION = "organization"
    PERSON = "person"


class Party(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: ItemId
    name: str
    kind: PartyKind
    role: str
    evidence: list[Citation] = []
    ntsb: NtsbRef


class RelationType(StrEnum):
    CONTRACTED_WITH = "contracted_with"
    DESIGNED_FOR = "designed_for"
    REPRESENTED = "represented"  # acted as authorised representative of
    REVIEWED_SUBMITTALS_FOR = "reviewed_submittals_for"
    SUPPLIED = "supplied"
    SUBCONTRACTED_TO = "subcontracted_to"
    INSPECTED_FOR = "inspected_for"
    OVERSAW = "oversaw"  # had oversight or approval authority over


class Relationship(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: ItemId
    source: ItemId  # a Party id
    type: RelationType
    target: ItemId  # a Party id
    start: PartialDate | None = None
    end: PartialDate | None = None
    evidence: list[Citation]  # may be empty when only the NTSB report states it
    ntsb: NtsbRef
    split: Split


class AnswerKey(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    source: str  # the report the key is built from
    status: Status
    events: list[Event]
    negatives: list[Negative]
    parties: list[Party]
    relationships: list[Relationship]

    @model_validator(mode="after")
    def _consistent(self) -> "AnswerKey":
        ids = [
            *(e.id for e in self.events),
            *(n.id for n in self.negatives),
            *(p.id for p in self.parties),
            *(r.id for r in self.relationships),
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate item id")
        prefixes = {"E": self.events, "N": self.negatives, "P": self.parties, "R": self.relationships}
        for prefix, items in prefixes.items():
            for item in items:
                if not item.id.startswith(prefix):
                    raise ValueError(f"{item.id} should start with {prefix}")
        party_ids = {p.id for p in self.parties}
        for r in self.relationships:
            if r.source not in party_ids or r.target not in party_ids:
                raise ValueError(f"{r.id} links a party that is not in the key")
        return self

    def check_against(self, case: CaseConfig) -> list[str]:
        """Problems that make the key unusable for this case: evidence the agent cannot read."""
        readable = set(case.readable())
        problems = []
        for item in [*self.events, *self.relationships]:
            for c in item.evidence:
                if c.file_no not in readable:
                    problems.append(f"{item.id} cites file {c.file_no}, which the agent cannot read")
        for n in self.negatives:
            for f in n.must_have_read:
                if f not in readable:
                    problems.append(f"{n.id} relies on file {f}, which the agent cannot read")
        return problems


def normalise_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
