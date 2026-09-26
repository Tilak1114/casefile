"""Typed records for a public docket and the raw files fetched from it."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SourceEntry(BaseModel):
    """One file listed in the docket, as published by the NTSB."""

    model_config = ConfigDict(frozen=True)

    file_no: int = Field(ge=1)
    blob_id: str = Field(pattern=r"^\d+$")
    filename: str = Field(min_length=1)


class SourceIndex(BaseModel):
    model_config = ConfigDict(frozen=True)

    docket_id: str
    docket_url: HttpUrl
    files: list[SourceEntry]


class RawFile(BaseModel):
    """A fetched file: where it came from and exactly what was received."""

    model_config = ConfigDict(frozen=True)

    docket_id: str
    file_no: int
    filename: str
    source_url: HttpUrl
    path: str  # relative to the case directory
    sha256: Sha256
    bytes: int = Field(gt=0)
    retrieved_at: datetime


class FetchManifest(BaseModel):
    docket_id: str
    files: list[RawFile]
