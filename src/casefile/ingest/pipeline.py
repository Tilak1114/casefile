"""Ingest a case: parse and split every readable file, build page text and documents, store them."""

import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from pymongo.database import Database

from casefile.case import CaseConfig
from casefile.sources.models import FetchManifest
from casefile.ingest.clean import page_text
from casefile.ingest.models import (
    FileIngest,
    IngestRun,
    LogicalDocument,
    PageText,
    ReductoBlock,
    SplitSection,
)
from casefile.ingest.reducto import ReductoClient
from casefile.ingest.taxonomy import PRODUCTION_LABEL, SPLIT_RULES, split_description

MAX_PARALLEL = 8


def blocks_by_page(parse: dict) -> dict[int, list[ReductoBlock]]:
    pages: dict[int, list[ReductoBlock]] = defaultdict(list)
    for chunk in parse["result"]["chunks"]:
        for raw in chunk["blocks"]:
            block = ReductoBlock.model_validate(raw)
            pages[block.bbox.page].append(block)
    return pages


def documents_from_split(case_id: str, file_no: int, split: dict) -> list[LogicalDocument]:
    """One document per partition, or per section when Split found no partitions."""
    found: list[tuple[str, list[int], str, str]] = []
    for raw in split["result"]["splits"]:
        section = SplitSection.model_validate(raw)
        if not section.pages:
            continue
        if section.partitions:
            for part in section.partitions:
                if part.pages:
                    found.append((section.name, sorted(part.pages), part.name, part.conf))
        else:
            found.append((section.name, sorted(section.pages), section.name, section.conf))
    found.sort(key=lambda d: d[1][0])
    return [
        LogicalDocument(
            case_id=case_id, file_no=file_no, index=i, doc_type=doc_type,
            pages=pages, split_label=label, confidence=conf,
        )
        for i, (doc_type, pages, label, conf) in enumerate(found, start=1)
    ]


def ingest_file(
    reducto: ReductoClient, case_id: str, file_no: int, path: Path, sha256: str
) -> tuple[list[PageText], list[LogicalDocument], FileIngest]:
    parse, parse_cached = reducto.parse(path, sha256)
    request = {"split_description": split_description(), "split_rules": SPLIT_RULES}
    split, split_cached = reducto.split(path, sha256, parse["job_id"], request)
    documents = documents_from_split(case_id, file_no, split)

    label_pages = {p for d in documents if d.doc_type == PRODUCTION_LABEL for p in d.pages}
    assigned = {p for d in documents for p in d.pages}
    by_page = blocks_by_page(parse)
    n_pages = parse["usage"]["num_pages"]
    pages = []
    for number in range(1, n_pages + 1):
        text, spans, stripped, figures = page_text(by_page.get(number, []))
        pages.append(
            PageText(
                case_id=case_id, file_no=file_no, page=number, text=text, blocks=spans,
                stripped=stripped, figures_dropped=figures, is_label=number in label_pages,
            )
        )
    summary = FileIngest(
        case_id=case_id, file_no=file_no, sha256=sha256, pages=n_pages, documents=len(documents),
        label_pages=len(label_pages),
        unassigned_pages=[p for p in range(1, n_pages + 1) if p not in assigned],
        parse_credits=0.0 if parse_cached else parse["usage"]["credits"],
        split_credits=0.0 if split_cached else split["usage"]["credits"],
        cached=parse_cached and split_cached,
    )
    return pages, documents, summary


def store(db: Database, pages: list[PageText], documents: list[LogicalDocument]) -> None:
    """Replace everything stored for these files, so a re-split never leaves stale documents behind."""
    for file_key in {(p.case_id, p.file_no) for p in pages}:
        selector = {"case_id": file_key[0], "file_no": file_key[1]}
        db.pages.delete_many(selector)
        db.documents.delete_many(selector)
    if pages:
        db.pages.insert_many([{"_id": p.id, **p.model_dump(mode="json")} for p in pages])
    if documents:
        db.documents.insert_many(
            [{"_id": d.id, **d.model_dump(mode="json"), "is_label": d.is_label} for d in documents]
        )


def ingest_case(
    case: CaseConfig, manifest: FetchManifest, case_dir: Path, reducto: ReductoClient, db: Database
) -> IngestRun:
    started = datetime.now(UTC)
    readable = set(case.readable())
    files = [f for f in manifest.files if f.file_no in readable]
    results: list[FileIngest] = []
    failures: list[str] = []
    with ThreadPoolExecutor(MAX_PARALLEL) as pool:
        jobs = {
            pool.submit(ingest_file, reducto, case.case_id, f.file_no, case_dir / f.path, f.sha256): f
            for f in files
        }
        for job in as_completed(jobs):
            f = jobs[job]
            try:
                pages, documents, summary = job.result()
            except Exception as exc:  # report each failure as it happens
                failures.append(f"file {f.file_no}: {exc}")
                print(failures[-1], file=sys.stderr, flush=True)
                continue
            store(db, pages, documents)
            results.append(summary)
            print(
                f"file {f.file_no}: {summary.pages} pages, {summary.documents} documents, "
                f"{summary.label_pages} label pages"
                + (f", unassigned {summary.unassigned_pages}" if summary.unassigned_pages else "")
                + (" (cached)" if summary.cached else ""),
                flush=True,
            )
    run = IngestRun(
        case_id=case.case_id, started_at=started, finished_at=datetime.now(UTC),
        files=sorted(results, key=lambda r: r.file_no), failures=failures,
    )
    db.ingest_runs.insert_one(run.model_dump(mode="json"))
    return run
