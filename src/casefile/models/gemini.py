"""Gemini behind one interface: typed output, cached on disk, spending only when allowed."""

import hashlib
import json
from pathlib import Path
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from casefile.blobstore import CacheStore

T = TypeVar("T", bound=BaseModel)


class SpendNotAllowed(RuntimeError):
    pass


class GeminiUsage(BaseModel):
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0


class Gemini:
    def __init__(self, api_key: str | None, model: str, cache_dir: Path, allow_spend: bool = False):
        self.model = model
        self.cache_dir = cache_dir
        self.cache = CacheStore(cache_dir)
        self.allow_spend = allow_spend
        self._client = genai.Client(api_key=api_key) if api_key else None

    def _key(self, task: str, prompt: str, schema: type[BaseModel]) -> Path:
        digest = hashlib.sha256(
            json.dumps([self.model, prompt, schema.model_json_schema()], sort_keys=True).encode()
        ).hexdigest()[:24]
        return self.cache_dir / f"{task}-{digest}.json.gz"

    def structured(self, task: str, prompt: str, schema: type[T]) -> tuple[T, GeminiUsage, bool]:
        """Model output validated into `schema`, its token usage, and whether it came from the cache."""
        path = self._key(task, prompt, schema)
        if (cached := self.cache.get(path.name)) is not None:
            return schema.model_validate(cached["output"]), GeminiUsage.model_validate(cached["usage"]), True
        if not self.allow_spend:
            raise SpendNotAllowed(f"Gemini {task} needed but not in the cache; rerun with --allow-spend")
        if self._client is None:
            raise RuntimeError("GEMINI_TOKEN is not set")
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0, response_mime_type="application/json", response_schema=schema
            ),
        )
        output = schema.model_validate_json(response.text)
        meta = response.usage_metadata
        usage = GeminiUsage(
            prompt_tokens=meta.prompt_token_count or 0,
            output_tokens=meta.candidates_token_count or 0,
            thinking_tokens=meta.thoughts_token_count or 0,
        )
        self.cache.put(path.name, {"model": self.model, "output": output.model_dump(mode="json"), "usage": usage.model_dump()})
        return output, usage, False
