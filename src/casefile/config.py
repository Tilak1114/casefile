"""Settings loaded from `.env`."""

from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    atlas_connection_string: str  # the team database: the team Atlas cluster
    casefile_database: str
    gemini_token: str | None = None
    gemini_model: str | None = None
    reducto_api_key: str | None = None


@lru_cache
def settings() -> Settings:
    raw = dotenv_values(REPO_ROOT / ".env")
    # Keys are stripped because a stray space before "=" once made a key unreadable.
    values = {k.strip().lower(): v for k, v in raw.items() if v is not None}
    return Settings.model_validate(values)
