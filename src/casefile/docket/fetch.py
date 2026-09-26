"""Fetch a public NTSB docket's files to disk and record what was received."""

import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx

from casefile.docket.models import FetchManifest, RawFile, SourceEntry, SourceIndex

BLOB_URL = "https://data.ntsb.gov/Docket/Document/docBLOB"
MAX_PARALLEL = 8


def blob_url(entry: SourceEntry) -> str:
    return (
        f"{BLOB_URL}?ID={entry.blob_id}&FileExtension=.PDF"
        f"&FileName={quote(entry.filename)}"
    )


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_one(client: httpx.Client, docket_id: str, entry: SourceEntry, raw_dir: Path) -> RawFile:
    url = blob_url(entry)
    path = raw_dir / f"{entry.file_no:03d}.pdf"
    if not path.exists():
        response = client.get(url)
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"):
            raise ValueError(f"file {entry.file_no}: response is not a PDF")
        path.write_bytes(response.content)
    return RawFile(
        docket_id=docket_id,
        file_no=entry.file_no,
        filename=entry.filename,
        source_url=url,
        path=str(path.relative_to(raw_dir.parent)),
        sha256=sha256_of(path),
        bytes=path.stat().st_size,
        retrieved_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
    )


def fetch_docket(index: SourceIndex, case_dir: Path, client: httpx.Client) -> FetchManifest:
    raw_dir = case_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fetched: list[RawFile] = []
    failures: list[str] = []
    with ThreadPoolExecutor(MAX_PARALLEL) as pool:
        jobs = {
            pool.submit(fetch_one, client, index.docket_id, entry, raw_dir): entry
            for entry in index.files
        }
        for job in as_completed(jobs):
            entry = jobs[job]
            try:
                fetched.append(job.result())
            except Exception as exc:  # report each failure as soon as it happens
                message = f"file {entry.file_no} failed: {exc}"
                failures.append(message)
                print(message, file=sys.stderr, flush=True)
    if failures:
        raise RuntimeError(f"{len(failures)} of {len(index.files)} files failed to fetch")
    fetched.sort(key=lambda f: f.file_no)
    manifest = FetchManifest(docket_id=index.docket_id, files=fetched)
    (case_dir / "fetch_manifest.json").write_text(manifest.model_dump_json(indent=1))
    return manifest
