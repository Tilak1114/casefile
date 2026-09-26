"""Shared storage in Atlas for everything paid for or fetched once: vendor and model response caches, and
source files. A teammate with the Atlas connection string needs nothing else.

Caches live in the `cache` collection (gzipped JSON, keyed by the same file name as the local cache);
source files live in GridFS. Local files remain a fallback for offline work.
"""

import gzip
import json
from pathlib import Path

import gridfs
from bson.binary import Binary
from pymongo.database import Database

from casefile import db as dbmod


def _db() -> Database:
    return dbmod.database()


class CacheStore:
    """Read-through cache: Atlas first, then the local file; writes go to both."""

    def __init__(self, local_dir: Path, db: Database | None = None):
        self.local_dir = local_dir
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self._db = db

    @property
    def collection(self):
        return (self._db or _db()).cache

    def get(self, name: str) -> dict | None:
        doc = self.collection.find_one({"_id": name})
        if doc is not None:
            return json.loads(gzip.decompress(doc["data"]))
        path = self.local_dir / name
        if path.exists():
            with gzip.open(path, "rt") as fh:
                return json.load(fh)
        return None

    def put(self, name: str, body: dict) -> None:
        raw = gzip.compress(json.dumps(body).encode())
        (self.local_dir / name).write_bytes(raw)
        self.collection.replace_one({"_id": name}, {"_id": name, "data": Binary(raw), "bytes": len(raw)}, upsert=True)

    def upload_local(self) -> int:
        """Copy every local cache file into Atlas (idempotent)."""
        n = 0
        for path in sorted(self.local_dir.glob("*.json.gz")):
            if self.collection.count_documents({"_id": path.name}, limit=1):
                continue
            raw = path.read_bytes()
            self.collection.insert_one({"_id": path.name, "data": Binary(raw), "bytes": len(raw)})
            n += 1
        return n


def upload_sources(case_id: str, files: list[tuple[int, Path, str]], db: Database | None = None) -> int:
    """Store source files in GridFS as `<case_id>/<file_no>.pdf`, with their SHA-256 (idempotent)."""
    fs = gridfs.GridFS(db or _db(), collection="sources")
    n = 0
    for file_no, path, sha256 in files:
        name = f"{case_id}/{file_no:03d}.pdf"
        if fs.exists({"filename": name, "metadata.sha256": sha256}):
            continue
        with path.open("rb") as fh:
            fs.put(fh, filename=name, metadata={"case_id": case_id, "file_no": file_no, "sha256": sha256})
        n += 1
    return n


def read_source(case_id: str, file_no: int, db: Database | None = None) -> bytes:
    fs = gridfs.GridFS(db or _db(), collection="sources")
    return fs.get_last_version(filename=f"{case_id}/{file_no:03d}.pdf").read()
