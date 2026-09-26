"""Model calls through OpenRouter: typed output, cached in Atlas, spending only when allowed.

Same interface as the Gemini client (`structured(task, prompt, schema)`), so agents do not care which
gateway serves them. Every answer is cached by model, prompt and schema, so a finished run replays for free.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel

from casefile.blobstore import CacheStore

T = TypeVar("T", bound=BaseModel)
URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.8-flash"
RATE_LIMIT_RETRIES = 5  # a 429 is retried more often than other errors, with longer waits


class SpendNotAllowed(RuntimeError):
    pass


class ModelUsage(BaseModel):
    prompt_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    reasoning: str = ""  # the provider's summary of the model's reasoning, when it returns one (not the raw tokens)


class OpenRouter:
    def __init__(self, api_key: str | None, cache_dir: Path, model: str = DEFAULT_MODEL, allow_spend: bool = False,
                 http: httpx.Client | None = None, retries: int = 2, read_cache: bool = True):
        self.model = model
        self.cache = CacheStore(cache_dir)
        self.allow_spend = allow_spend
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=600)
        self.retries = retries
        self.read_cache = read_cache  # False: always call the model (answers are still written to the cache)

    def _key(self, task: str, prompt: str, schema: type[BaseModel]) -> str:
        digest = hashlib.sha256(
            json.dumps(["openrouter", self.model, prompt, schema.model_json_schema()], sort_keys=True).encode()
        ).hexdigest()[:24]
        return f"{task}-{digest}.json.gz"

    def structured(self, task: str, prompt: str, schema: type[T]) -> tuple[T, ModelUsage, bool]:
        """Model output validated into `schema`, its usage, and whether it came from the cache."""
        name = self._key(task, prompt, schema)
        if self.read_cache and (cached := self.cache.get(name)) is not None:
            return schema.model_validate(cached["output"]), ModelUsage.model_validate(cached["usage"]), True
        if not self.allow_spend:
            raise SpendNotAllowed(f"model call {task} needed but not in the cache; rerun with --allow-spend")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API is not set")
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
            "reasoning": {"exclude": False},  # return the reasoning summary with the answer
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()}},
        }
        output = None
        attempt = 0
        while True:
            response = self.http.post(URL, headers={"Authorization": f"Bearer {self.api_key}"}, json=body)
            data = response.json() if response.status_code == 200 else {}
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
            if content:
                try:
                    output = schema.model_validate_json(content)
                    break
                except ValueError:
                    pass  # malformed JSON from the model: retry
            limited = response.status_code == 429
            transient = response.status_code in (200, 408, 429, 500, 502, 503, 504)
            if not transient or attempt >= (RATE_LIMIT_RETRIES if limited else self.retries):
                raise RuntimeError(f"OpenRouter {task} returned {response.status_code} without valid output: {response.text[:300]}")
            if limited:  # a per-minute limit: wait as told, or long enough for the window to move
                time.sleep(float(response.headers.get("retry-after") or 0) or 15 * (attempt + 1))
            else:
                time.sleep(2 * (attempt + 1))
            attempt += 1
        u = data.get("usage", {})
        message = (data.get("choices") or [{}])[0].get("message") or {}
        usage = ModelUsage(
            prompt_tokens=u.get("prompt_tokens", 0), output_tokens=u.get("completion_tokens", 0),
            reasoning_tokens=(u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0,
            cost_usd=u.get("cost", 0.0) or 0.0, reasoning=message.get("reasoning") or "",
        )
        self.cache.put(name, {"model": self.model, "output": output.model_dump(mode="json"), "usage": usage.model_dump()})
        return output, usage, False
