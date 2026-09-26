# Casefile: plan (superseded)

> Superseded on 2026-09-26. The case is now the real NTSB docket HWY06MH024, the database is local
> MongoDB, and ingestion uses Reducto. See `DECISIONS.md` and the step documents `00-*` to `02-*`.
> Kept for the reasoning behind the verifier and coverage design.

Status on 2026-09-25: repo created, nothing built. The hackathon (MongoDB Harness Engineering & Model
Wrangling) is on 2026-09-26. Statement One is recursive harnessing, Statement Two is long-horizon
engineering. Judging: demo 35%, difficulty 25%, creativity 25%, impact 15%. The repo must be public,
with a one-minute video and a three-minute live demo.

## Open decision (settle first)

**Domain.** The working choice is AEC insurance, meaning architecture, engineering and construction
claims such as a failed cladding or flashing detail causing water intrusion. If the builder does not
know AEC well, pick a document-heavy investigation they do know, such as an insurance claim, an audit
or an incident review. The harness is the same; only the synthetic case changes. Judges will ask
domain questions.

## Why this exists

We built PerceptFlow, a verified question-answering harness over video. It had a LangGraph loop,
typed claims checked against evidence, and "nothing happened" claims that had to cite coverage. We
tested its perception against MEVA's independent labels (CC-BY-4.0 multi-camera security footage):

- Object pick-ups: 2 of 60 found.
- Door crossings: worked on one close camera (about 80–87% found, about 3% false), then collapsed on
  5 unseen cameras (14 of 89 entries, 18 of 122 exits).
- Gemini watching the clips directly roughly doubled recall on unfamiliar cameras. It still missed most
  events on wide or distant views, and it gives no evidence a verifier can check.

On video, the checking step is only as good as perception, and perception is not reliable on real
footage. With documents it is the other way round: checking a claim is cheap and exact, because a
quoted passage either exists in the source or it doesn't. So we keep the harness and change the
evidence.

## The pitch

A forensic engineer spends months reading RFIs, change orders, submittals and emails to find who
approved a failed detail. Casefile reads the whole project record and produces the timeline an
adjuster can take into subrogation:
- every line quotes its source;
- every "no approval exists" shows exactly what was searched;
- it learns each vendor's file formats as it goes.

It does not decide liability, which is a legal finding. It produces the evidence timeline and the adjuster decides.

"Why not paste everything into Gemini?" A real claim file is thousands of documents, more than fits in
one prompt. A carrier also cannot accept a summary nobody can audit, while every claim Casefile makes
is checkable.

## Design

1. **Exact-quote verifier.** Every claim, meaning a timeline entry or a finding, cites
   `(document_id, quote)`. The verifier checks that the quote occurs in the stored text of that
   document after whitespace normalisation, plus any typed fields (date, author, document type) the
   claim asserts. Claims that fail are refused, not softened. A claim with no citation is marked
   interpretation.
2. **Coverage and negatives.** Every read or search records what it covered: which documents, of which
   type, in which date range. A negative ("no approval for change order 14 exists") must cite a
   coverage record that spans the relevant documents and window. The run ends when coverage of the case
   file is complete, or explicitly reports what was not read.
3. **Long horizon.** A case holds hundreds to thousands of documents. The run is a LangGraph loop
   checkpointed to Atlas, so it can be interrupted and resumed. Context is compacted, and findings are
   stored as verified records, not kept in the prompt.
4. **Recursive harnessing, the honest version.** When a file fails to parse because of an unfamiliar
   vendor format, the agent writes a parser. The parser is accepted only if it passes fixed checks:
   - it extracts records;
   - required fields are present;
   - dates are valid;
   - every extracted field value is found in the raw bytes, so nothing is invented.

   Accepted parsers are saved in an Atlas registry keyed by format signature and reused. The
   measurable claim is that a second case using the same vendor format needs no new parser. Nothing
   else rewrites itself.
5. **Outputs.** These are real deliverables, not chat:
   - a timeline, as markdown or PDF, with a citation on every line;
   - an evidence exhibit list (document, quote, hash of the source file);
   - a coverage and gaps report.

## What to leave out

- A harness that rewrites its own prompts or policy, auto-tuning, proposing rules, and pausing for a
  human in the loop. All of these were built in PerceptFlow and removed as unproven.
- "Proves liability", "flawless", "AI hallucination liability". These are hype.
- Dashboards as the main feature.

## Data

There is no public AEC claim file, so the case is synthetic, and we say so on stage: "synthetic case,
real formats, the chain is planted so we can score it". One project should include:
- emails (`.eml`);
- RFI and change-order logs (CSV or XLSX);
- submittals and specs (PDF);
- meeting minutes;
- one deliberately unusual vendor log format that no built-in parser handles.

Plant one failure chain, for example "spec section X revised by a design script; the submittal
approved by engineer Y without review; flashing installed per the revised detail; leak reported".
Surround it with plenty of irrelevant documents. Write the answer key separately. It is the eval: which
documents and quotes must appear in the timeline, and which negatives must hold.

## Build order

Build the checks first, then the agent, then the demo.
1. Scaffold: uv, Python 3.12, a Gemini model port, Atlas connection from `.env` using database
   `CASEFILE_DATABASE`, and pytest.
2. The case generator and answer key, deterministic and seeded.
3. Ingest documents into Atlas: raw file, extracted text, metadata, and a hash of the source file.
4. The exact-quote verifier and coverage records, with tests first. These decide whether the demo holds up.
5. Tools: search documents (text plus vector search in Atlas), read a document, list documents by
   type and date, parse a file, and write a parser (sandboxed, then checked, then saved to the
   registry).
6. The LangGraph loop, with the Atlas checkpointer and guards.
7. The report writer: timeline, exhibits, coverage.
8. Eval against the answer key, a second case that reuses the vendor format, then the demo script.

## Reference code in PerceptFlow

The PerceptFlow code is at `/Users/tilaksharma/VsCodeProjects/sentinal/perceptflow/src/perceptflow/`.
Port the ideas; copy code only where it transfers cleanly.
- `harness/verify.py`: typed claims, refusing uncited or mismatched claims, negatives that must cite coverage.
- `harness/graph.py`, `harness/nodes.py`, `harness/state.py`: the loop (decide, validate, execute,
  normalize, verify, finish, budget stop) and guards. The guards are constants: at most 2 overlapping
  repeats, at most 3 unproductive steps in a row, at most 6 calls per tool.
- `harness/context.py`: compaction, keeping the 6 most recent turns.
- `models/port.py`, `models/gemini.py`: a model port that keeps Gemini behind one interface.
- `memory/db.py`, `memory/runs.py`, `memory/threads.py`: the Atlas connection, the checkpointer, and runs.
- `harness/architecture.py`: a harness diagram generated from the code.
- `api/app.py`, `api/static/index.html`: a FastAPI app and a single-page UI with a dark theme and an amber accent.

## Constraints

- Gemini is the only model provider. Atlas is the only database, from `.env`. It is on the free tier
  with a 512 MB cap, and PerceptFlow's data already lives there. If space runs out, PerceptFlow's
  checkpoint collections in database `perceptflow` can be dropped.
- Evals are regression suites, not benchmarks. Report failures plainly.
