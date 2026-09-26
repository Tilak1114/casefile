import json

import httpx
import pytest
from pydantic import BaseModel

from casefile.models import openrouter
from casefile.models.openrouter import OpenRouter, SpendNotAllowed


class Answer(BaseModel):
    ok: bool


class MemoryCache:
    def __init__(self, *_):
        self.store: dict = {}

    def get(self, name):
        return self.store.get(name)

    def put(self, name, body):
        self.store[name] = body


@pytest.fixture(autouse=True)
def memory_cache(monkeypatch):
    monkeypatch.setattr(openrouter, "CacheStore", MemoryCache)


def reply(status=200, content='{"ok": true}'):
    body = {"choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 5, "cost": 2.8e-06,
                      "completion_tokens_details": {"reasoning_tokens": 2}}}
    return httpx.Response(status, json=body if status == 200 else {"error": "busy"})


def client(handler, **kw):
    return OpenRouter("key", cache_dir=None, allow_spend=True, http=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def test_structured_output_usage_and_cache():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return reply()

    c = client(handler)
    out, usage, cached = c.structured("t", "prompt", Answer)
    assert out.ok and not cached and usage.cost_usd == 2.8e-06 and usage.reasoning_tokens == 2
    assert calls[0]["model"] == "google/gemini-3.8-flash"
    assert calls[0]["response_format"]["json_schema"]["schema"]["properties"]["ok"]["type"] == "boolean"
    _, _, cached = c.structured("t", "prompt", Answer)
    assert cached and len(calls) == 1


def test_no_spend_without_permission():
    c = OpenRouter("key", cache_dir=None, allow_spend=False,
                   http=httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("no call allowed"))))
    with pytest.raises(SpendNotAllowed):
        c.structured("t", "prompt", Answer)


def test_retries_once_on_transient_error(monkeypatch):
    monkeypatch.setattr(openrouter.time, "sleep", lambda s: None)
    responses = [reply(503), reply()]
    out, _, _ = client(lambda r: responses.pop(0)).structured("t", "p", Answer)
    assert out.ok and responses == []


def test_gives_up_on_permanent_error():
    with pytest.raises(RuntimeError, match="400"):
        client(lambda r: reply(400)).structured("t", "p", Answer)
