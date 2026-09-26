# Casefile

An agent harness that reconstructs a construction project's record into a cited chronology and party
map. Every line quotes its source, and every negative finding shows what was read.

The demo case is the public NTSB docket HWY06MH024 (Boston I-90 connector tunnel ceiling collapse,
2006), used unaltered. See `docs/DECISIONS.md` for every decision made so far, and `docs/00-*` to
`docs/02-*` for the step plans.

## Setup for teammates (no paid calls)

The team database is the team MongoDB Atlas cluster; it already holds the ingested case and the
Atlas Search index. Everything paid is also in the repo: Reducto's parse and split results and
Gemini's metadata are cached under `data/cases/HWY06MH024/cache/`, and the database is snapshotted in
`data/snapshots/`.

```bash
cp .env.example .env            # set ATLAS_CONNECTION_STRING to the Atlas connection string, add GEMINI_TOKEN/GEMINI_MODEL
uv sync
uv run casefile ping            # checks the connection
uv run casefile fetch           # downloads the 94 public NTSB PDFs (free), for page images and re-ingest
```

Working offline instead: `docker compose up -d --wait`, point `ATLAS_CONNECTION_STRING` at
`mongodb://localhost:27017/?directConnection=true`, then `uv run casefile snapshot-restore` and
`uv run casefile indexes`. Restoring refuses to overwrite a non-local database unless you pass
`--yes-replace-shared`.

`casefile ingest` and `casefile metadata` read the committed caches and refuse to call Reducto or
Gemini for anything missing unless run with `--allow-spend`. After any paid run, commit the new cache
files and run `casefile snapshot-export` so nobody pays for the same work again.

## MongoDB MCP server

`.mcp.json` registers the official MongoDB MCP server (read-only) for Claude Code, pointing at local
Mongo by default. To point it at the Atlas cluster without committing credentials, export
`MDB_MCP_CONNECTION_STRING` before starting Claude Code, or add a machine-local override with
`claude mcp add-json mongodb '<config>' --scope local`.

## Tests

```bash
uv run pytest                   # unit tests
uv run pytest -m integration    # needs the Mongo container and an ingested database
```
