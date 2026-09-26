# Casefile

An agent harness that reconstructs a construction project's record into a cited chronology and party
map. Every line quotes its source, and every negative finding shows what was read.

The demo case is the public NTSB docket HWY06MH024 (Boston I-90 connector tunnel ceiling collapse,
2006), used unaltered. See `docs/DECISIONS.md` for every decision made so far, and `docs/00-*` to
`docs/02-*` for the step plans.

## Setup for teammates (no paid calls)

Everything paid is already in the repo: Reducto's parse and split results are cached in
`data/cases/HWY06MH024/cache/reducto/`, and the database is snapshotted in `data/snapshots/`.

```bash
cp .env.example .env            # add GEMINI_TOKEN and GEMINI_MODEL; REDUCTO_API_KEY is not needed
docker compose up -d --wait     # local MongoDB with Atlas Search (mongodb-atlas-local)
uv sync
uv run casefile fetch           # downloads the 94 public docket PDFs from the NTSB (free)
uv run casefile snapshot-restore   # load the database as ingested
```

Or rebuild the database from the cache instead of the snapshot, still at no cost:

```bash
uv run casefile ingest          # reads the committed Reducto cache; 0 credits
```

`casefile ingest` refuses to call Reducto for anything missing from the cache unless run with
`--allow-spend`. After any paid run, commit the new cache files and run `casefile snapshot-export`
so nobody pays for the same work again.

## Tests

```bash
uv run pytest                   # unit tests
uv run pytest -m integration    # needs the Mongo container and an ingested database
```
