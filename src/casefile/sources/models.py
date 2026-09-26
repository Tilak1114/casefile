"""Typed records for a case's source files: where each came from and exactly what was received."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SourceEntry(BaseModel):
    """One file listed by the source (for the demo, the NTSB docket)."""

    model_config = ConfigDict(frozen=True)

    file_no: int = Field(ge=1)
    blob_id: str = Field(pattern=r"^\d+$")
    filename: str = Field(min_length=1)


class SourceIndex(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    source_url: HttpUrl
    files: list[SourceEntry]


class RawFile(BaseModel):
    """A fetched file: where it came from and exactly what was received."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    file_no: int
    filename: str
    source_url: HttpUrl
    path: str  # relative to the case directory
    sha256: Sha256
    bytes: int = Field(gt=0)
    retrieved_at: datetime


class FetchManifest(BaseModel):
    case_id: str
    files: list[RawFile]
