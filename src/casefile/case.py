"""Which of a case's files the agent may read, and why the rest are withheld."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FileGroup(StrEnum):
    INPUT = "input"  # what a claims examiner would receive; the agent reads these
    WITHHELD = "withheld"  # the investigator's own analysis: same kind of thing as our outputs; answer key only
    UNPLACED = "unplaced"  # not yet classified; withheld until it is


class FileAssignment(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_no: int = Field(ge=1)
    group: FileGroup
    reason: str = Field(min_length=1)


class CaseConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    title: str
    event_date: date
    event_summary: str
    files: list[FileAssignment]

    @model_validator(mode="after")
    def _unique_files(self) -> "CaseConfig":
        numbers = [f.file_no for f in self.files]
        if len(numbers) != len(set(numbers)):
            raise ValueError("a file is assigned more than once")
        return self

    def readable(self) -> list[int]:
        return sorted(f.file_no for f in self.files if f.group is FileGroup.INPUT)

    def withheld(self) -> list[FileAssignment]:
        return [f for f in self.files if f.group is not FileGroup.INPUT]
