"""Command line entry point."""

import argparse

import httpx

from casefile import db, search, snapshot
from casefile.config import DATA_DIR
from casefile.sources.ntsb import fetch_files
from casefile.case import CaseConfig
from casefile.sources.models import FetchManifest, SourceIndex
from casefile.config import settings
from casefile.ingest.metadata import extract_case
from casefile.ingest.pipeline import ingest_case
from casefile.models.gemini import Gemini
from casefile.ingest.reducto import ReductoClient


def cmd_fetch(args: argparse.Namespace) -> None:
    case_dir = DATA_DIR / "cases" / args.case
    index = SourceIndex.model_validate_json((case_dir / "source_index.json").read_text())
    with httpx.Client(timeout=120, headers={"User-Agent": "casefile/0.1"}) as http:
        manifest = fetch_files(index, case_dir, http)
    total = sum(f.bytes for f in manifest.files)
    print(f"{len(manifest.files)} files, {total / 1e6:.1f} MB -> {case_dir / 'raw'}")


def cmd_ingest(args: argparse.Namespace) -> None:
    case_dir = DATA_DIR / "cases" / args.case
    case = CaseConfig.model_validate_json((case_dir / "case.json").read_text())
    manifest = FetchManifest.model_validate_json((case_dir / "fetch_manifest.json").read_text())
    reducto = ReductoClient(settings().reducto_api_key, case_dir / "cache" / "reducto", allow_spend=args.allow_spend)
    run = ingest_case(case, manifest, case_dir, reducto, db.database())
    credits = sum(f.parse_credits + f.split_credits for f in run.files)
    print(f"{len(run.files)} files ingested, {len(run.failures)} failed, {credits:.1f} Reducto credits")


def cmd_metadata(args: argparse.Namespace) -> None:
    case_dir = DATA_DIR / "cases" / args.case
    config = settings()
    gemini = Gemini(config.gemini_token, config.gemini_model or "", case_dir / "cache" / "gemini", allow_spend=args.allow_spend)
    totals = extract_case(db.database(), args.case, gemini)
    print(totals)


SNAPSHOT = DATA_DIR / "snapshots" / "casefile.archive.gz"


def cmd_snapshot_export(_: argparse.Namespace) -> None:
    snapshot.export(SNAPSHOT)
    print(f"database exported to {SNAPSHOT} ({SNAPSHOT.stat().st_size / 1e6:.1f} MB)")


def cmd_snapshot_restore(args: argparse.Namespace) -> None:
    uri = settings().atlas_connection_string
    local = "localhost" in uri or "127.0.0.1" in uri
    if not local and not args.yes_replace_shared:
        raise SystemExit(
            "ATLAS_CONNECTION_STRING is a shared cluster; restoring drops and replaces its casefile "
            "collections. Rerun with --yes-replace-shared if that is what you want."
        )
    snapshot.restore(SNAPSHOT)
    print(f"database restored from {SNAPSHOT} to {'local' if local else 'the shared cluster'}")


def cmd_run(args: argparse.Namespace) -> None:
    from casefile.harness.run import run_case

    out = run_case(args.case, run_id=args.run_id, allow_spend=args.allow_spend)
    c = out.coverage
    print(f"{out.run_id}: {len(out.chronology)} chronology entries, {len(out.parties)} parties, "
          f"{len(out.links)} links, {len(out.negatives)} negatives; read {c.documents_read}/{c.documents_total} "
          f"documents, {c.pages_read}/{c.pages_total} pages")


def cmd_upload(args: argparse.Namespace) -> None:
    from casefile.blobstore import CacheStore, upload_sources

    case_dir = DATA_DIR / "cases" / args.case
    manifest = FetchManifest.model_validate_json((case_dir / "fetch_manifest.json").read_text())
    for kind in ("reducto", "gemini"):
        print(f"{kind} cache: {CacheStore(case_dir / 'cache' / kind).upload_local()} new entries uploaded")
    files = [(f.file_no, case_dir / f.path, f.sha256) for f in manifest.files]
    print(f"sources: {upload_sources(args.case, files)} new files uploaded to GridFS")


def cmd_baseline(args: argparse.Namespace) -> None:
    from pymongo import MongoClient

    from casefile.evaluation.baseline import run_baseline
    from casefile.harness.examiner import Deps
    from casefile.harness.store import RunStore
    from casefile.verify.coverage import CoverageLog
    from casefile.verify.load import load_index

    config = settings()
    database = MongoClient(config.atlas_connection_string)[config.casefile_database]
    case_dir = DATA_DIR / "cases" / args.case
    case = CaseConfig.model_validate_json((case_dir / "case.json").read_text())
    manifest = FetchManifest.model_validate_json((case_dir / "fetch_manifest.json").read_text())
    deps = Deps(gemini=Gemini(config.gemini_token, config.gemini_model or "", case_dir / "cache" / "gemini", allow_spend=args.allow_spend),
                index=load_index(database, args.case), store=RunStore(database, args.case, args.run_id),
                coverage=CoverageLog(database, args.case, args.run_id))
    print(run_baseline(deps, case, {f.file_no: f.sha256 for f in manifest.files}))


def cmd_assemble(args: argparse.Namespace) -> None:
    from pymongo import MongoClient

    from casefile.harness.assemble import assemble
    from casefile.harness.examiner import Deps
    from casefile.harness.store import RunStore
    from casefile.verify.coverage import CoverageLog
    from casefile.verify.load import load_index

    config = settings()
    database = MongoClient(config.atlas_connection_string)[config.casefile_database]
    case_dir = DATA_DIR / "cases" / args.case
    case = CaseConfig.model_validate_json((case_dir / "case.json").read_text())
    manifest = FetchManifest.model_validate_json((case_dir / "fetch_manifest.json").read_text())
    deps = Deps(gemini=None, index=load_index(database, args.case), store=RunStore(database, args.case, args.run_id),
                coverage=CoverageLog(database, args.case, args.run_id))
    out = assemble(deps, case, {f.file_no: f.sha256 for f in manifest.files})
    print(f"{args.run_id}: {len(out.chronology)} chronology entries, {len(out.parties)} parties, {len(out.links)} links")


def cmd_score(args: argparse.Namespace) -> None:
    import yaml

    from casefile.evaluation.answer_key import AnswerKey
    from casefile.evaluation.score import score_run

    key = AnswerKey.model_validate(yaml.safe_load((DATA_DIR / "cases" / args.case / "answer_key.yaml").read_text()))
    s = score_run(db.database(), key, args.run_id)
    for name, sp in (("dev", s.dev), ("held-out", s.heldout)):
        print(f"{name:8} events {sp.events_found}/{sp.events_total} (core {sp.core_found}/{sp.core_total}), "
              f"relationships {sp.relationships_found}/{sp.relationships_total}")
    print(f"parties {s.parties_found}/{s.parties_total}; verified {s.verified_claims}, refused {s.refused_claims}; "
          f"pages read {s.pages_read}; readers {s.readers}; tokens in {s.prompt_tokens:,} out {s.output_tokens:,}; ~${s.cost_usd}")
    if args.missed:
        for m in s.dev.missed_events + s.heldout.missed_events:
            print("  missed:", m)


def cmd_indexes(_: argparse.Namespace) -> None:
    print("pages_text:", search.ensure_indexes(db.database()))


def cmd_ping(_: argparse.Namespace) -> None:
    print("mongo ok" if db.ping() else "mongo not ok")


def main() -> None:
    parser = argparse.ArgumentParser(prog="casefile")
    sub = parser.add_subparsers(required=True)
    fetch = sub.add_parser("fetch", help="download a case's source files (NTSB adapter)")
    fetch.add_argument("case", nargs="?", default="HWY06MH024")
    fetch.set_defaults(func=cmd_fetch)
    ingest = sub.add_parser("ingest", help="parse and split a case's readable files into Mongo")
    ingest.add_argument("case", nargs="?", default="HWY06MH024")
    ingest.add_argument("--allow-spend", action="store_true", help="call Reducto (paid) for files not in the cache")
    ingest.set_defaults(func=cmd_ingest)
    metadata = sub.add_parser("metadata", help="read each document's date, author and recipient with Gemini")
    metadata.add_argument("case", nargs="?", default="HWY06MH024")
    metadata.add_argument("--allow-spend", action="store_true", help="call Gemini (paid) for documents not in the cache")
    metadata.set_defaults(func=cmd_metadata)
    sub.add_parser("snapshot-export", help="write the database to data/snapshots").set_defaults(func=cmd_snapshot_export)
    restore = sub.add_parser("snapshot-restore", help="replace the database with data/snapshots")
    restore.add_argument("--yes-replace-shared", action="store_true", help="allow replacing a non-local database")
    restore.set_defaults(func=cmd_snapshot_restore)
    run = sub.add_parser("run", help="run the harness on a case (resumes if --run-id already exists)")
    run.add_argument("case", nargs="?", default="HWY06MH024")
    run.add_argument("--run-id")
    run.add_argument("--allow-spend", action="store_true", help="call Gemini (paid) for anything not cached")
    run.set_defaults(func=cmd_run)
    upload = sub.add_parser("upload", help="copy caches and source files into Atlas so teammates need only the connection string")
    upload.add_argument("case", nargs="?", default="HWY06MH024")
    upload.set_defaults(func=cmd_upload)
    base = sub.add_parser("baseline", help="single-prompt baseline: all readable pages in one Gemini call")
    base.add_argument("case", nargs="?", default="HWY06MH024")
    base.add_argument("--run-id", default="baseline-1")
    base.add_argument("--allow-spend", action="store_true")
    base.set_defaults(func=cmd_baseline)
    asm = sub.add_parser("assemble", help="re-assemble a finished run's outputs from its verified findings (no model calls)")
    asm.add_argument("run_id")
    asm.add_argument("case", nargs="?", default="HWY06MH024")
    asm.set_defaults(func=cmd_assemble)
    score = sub.add_parser("score", help="score a run against the answer key")
    score.add_argument("run_id")
    score.add_argument("case", nargs="?", default="HWY06MH024")
    score.add_argument("--missed", action="store_true", help="list the answer-key events the run did not find")
    score.set_defaults(func=cmd_score)
    sub.add_parser("indexes", help="create the Atlas Search index on page text").set_defaults(func=cmd_indexes)
    sub.add_parser("ping", help="check the MongoDB connection").set_defaults(func=cmd_ping)
    args = parser.parse_args()
    args.func(args)
