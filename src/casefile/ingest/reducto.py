"""Reducto parse and split, cached in the repo so a file is never paid for twice.

The cache is committed: anyone with the repo re-ingests for free. A cache miss calls Reducto only when
spending is explicitly allowed.
"""

import hashlib
import json
from pathlib import Path

import httpx

from casefile.blobstore import CacheStore

BASE_URL = "https://platform.reducto.ai"
PARSE_SETTINGS = {"settings": {"model": "r-1", "return_ocr_data": True}}
# Account-specific links (signed storage URL, studio page) are not kept in the shared cache.
PRIVATE_FIELDS = ("pdf_url", "studio_link")


class SpendNotAllowed(RuntimeError):
    pass


def _settings_hash(settings: dict) -> str:
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:12]


class ReductoClient:
    def __init__(
        self,
        api_key: str | None,
        cache_dir: Path,
        allow_spend: bool = False,
        http: httpx.Client | None = None,
    ):
        self.cache_dir = cache_dir
        self.cache = CacheStore(cache_dir)
        self.allow_spend = allow_spend
        self.api_key = api_key
        self.http = http or httpx.Client(base_url=BASE_URL, timeout=900)

    def _cache_path(self, sha256: str, kind: str, settings: dict) -> Path:
        return self.cache_dir / f"{sha256}-{kind}-{_settings_hash(settings)}.json.gz"

    def _read(self, path: Path) -> dict | None:
        return self.cache.get(path.name)

    def _write(self, path: Path, body: dict) -> None:
        self.cache.put(path.name, {k: v for k, v in body.items() if k not in PRIVATE_FIELDS})

    def _require_spend(self, what: str) -> None:
        if not self.allow_spend:
            raise SpendNotAllowed(f"Reducto {what} needed but not in the cache; rerun with --allow-spend to pay for it")

    def _post(self, path: str, **kwargs) -> dict:
        self._require_spend(path)
        if not self.api_key:
            raise RuntimeError("REDUCTO_API_KEY is not set")
        response = self.http.post(path, headers={"Authorization": f"Bearer {self.api_key}"}, **kwargs)
        if response.status_code != 200:
            raise RuntimeError(f"Reducto {path} returned {response.status_code}: {response.text[:300]}")
        body = response.json()
        # Large results come back as a short-lived URL instead of inline.
        result = body.get("result")
        if isinstance(result, dict) and result.get("type") == "url":
            body["result"] = httpx.get(result["url"], timeout=300).json()
        return body

    def upload(self, path: Path) -> str:
        with path.open("rb") as fh:
            return self._post("/upload", files={"file": (path.name, fh, "application/pdf")})["file_id"]

    def parse(self, path: Path, sha256: str) -> tuple[dict, bool]:
        """Parse response and whether it came from the cache."""
        cache = self._cache_path(sha256, "parse", PARSE_SETTINGS)
        if (cached := self._read(cache)) is not None:
            return cached, True
        self._require_spend(f"parse of {path.name}")
        body = self._post("/parse", json={"input": self.upload(path), **PARSE_SETTINGS})
        self._write(cache, body)
        return body, False

    def split(self, path: Path, sha256: str, parse_job_id: str, request: dict) -> tuple[dict, bool]:
        cache = self._cache_path(sha256, "split", request)
        if (cached := self._read(cache)) is not None:
            return cached, True
        self._require_spend(f"split of {path.name}")
        try:
            body = self._post("/split", json={"input": f"jobid://{parse_job_id}", **request})
        except SpendNotAllowed:
            raise
        except RuntimeError:
            # Parse jobs can expire; Split on the file itself costs the same (no extra parse charge).
            body = self._post("/split", json={"input": self.upload(path), **request})
        self._write(cache, body)
        return body, False
