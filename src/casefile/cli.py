"""Command line entry point."""

import argparse

import httpx

from casefile import db, snapshot
from casefile.config import DATA_DIR
from casefile.docket.fetch import fetch_docket
from casefile.docket.case import CaseConfig
from casefile.docket.models import FetchManifest, SourceIndex
from casefile.config import settings
from casefile.ingest.pipeline import ingest_case
from casefile.ingest.reducto import ReductoClient


def cmd_fetch(args: argparse.Namespace) -> None:
    case_dir = DATA_DIR / "cases" / args.case
    index = SourceIndex.model_validate_json((case_dir / "source_index.json").read_text())
    with httpx.Client(timeout=120, headers={"User-Agent": "casefile/0.1"}) as http:
        manifest = fetch_docket(index, case_dir, http)
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


SNAPSHOT = DATA_DIR / "snapshots" / "casefile.archive.gz"


def cmd_snapshot_export(_: argparse.Namespace) -> None:
    snapshot.export(SNAPSHOT)
    print(f"database exported to {SNAPSHOT} ({SNAPSHOT.stat().st_size / 1e6:.1f} MB)")


def cmd_snapshot_restore(_: argparse.Namespace) -> None:
    snapshot.restore(SNAPSHOT)
    print(f"database restored from {SNAPSHOT}")


def cmd_ping(_: argparse.Namespace) -> None:
    print("mongo ok" if db.ping() else "mongo not ok")


def main() -> None:
    parser = argparse.ArgumentParser(prog="casefile")
    sub = parser.add_subparsers(required=True)
    fetch = sub.add_parser("fetch", help="download a case's public docket files")
    fetch.add_argument("case", nargs="?", default="HWY06MH024")
    fetch.set_defaults(func=cmd_fetch)
    ingest = sub.add_parser("ingest", help="parse and split a case's readable files into Mongo")
    ingest.add_argument("case", nargs="?", default="HWY06MH024")
    ingest.add_argument("--allow-spend", action="store_true", help="call Reducto (paid) for files not in the cache")
    ingest.set_defaults(func=cmd_ingest)
    sub.add_parser("snapshot-export", help="write the database to data/snapshots").set_defaults(func=cmd_snapshot_export)
    sub.add_parser("snapshot-restore", help="replace the database with data/snapshots").set_defaults(func=cmd_snapshot_restore)
    sub.add_parser("ping", help="check the MongoDB connection").set_defaults(func=cmd_ping)
    args = parser.parse_args()
    args.func(args)
