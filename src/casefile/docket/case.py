"""Which docket files the agent may read, and why the rest are withheld."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FileGroup(StrEnum):
    PROJECT_RECORD = "project_record"  # made during the project; the agent reads these
    INVESTIGATION = "investigation"  # made by the investigation after the event; withheld
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
        return sorted(f.file_no for f in self.files if f.group is FileGroup.PROJECT_RECORD)

    def withheld(self) -> list[FileAssignment]:
        return [f for f in self.files if f.group is not FileGroup.PROJECT_RECORD]
