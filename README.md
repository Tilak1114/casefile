# Casefile

**A team of AI agents that reads an insurance claim file and rebuilds what happened, with every line quoted from the
documents and checked by code.**

Built for the MongoDB Harness Engineering & Model Wrangling hackathon, Statement Two (long-horizon agents).

## The problem

When a building or structure fails, the insurer's claim professional (the person who owns the claim and decides what
happens next) receives the *claim file*: contracts, submittals, letters, daily reports, test reports, photos. Before
anything can be decided, someone has to work out who did what, and when. Document review is about 73% of e-discovery
production cost ([RAND](https://www.rand.org/pubs/monographs/MG1208.html)); forensic experts bill about $422 an hour
for file review ([SEAK 2021](https://seak.com/wp-content/uploads/2021/03/2021-EW-Fee-Survey-Summary-Report.pdf)).

## What Casefile produces

From the claim file, and nothing else:

- **Chronology**: dated events in order, each with the exact quote and page it comes from.
- **Party map**: every company involved, the other names it goes by, and who contracted with, supplied or reviewed
  whom.
- **Absences**: what the record does *not* contain (for example, no creep testing of the adhesive before it was
  installed), each accepted only after every relevant page was read and a search found no counter-example.
- **Exhibit list and reading report**: every document cited (with its SHA-256), and which pages were read by whom.

Casefile quotes the record. It never states fault, cause or liability.

## The case: a real public record

The NTSB's public docket for the 2006 ceiling collapse in Boston's I-90 connector tunnel (HWY06MH024), used
unaltered: **88 source PDFs, 172 documents, 1,737 pages**. The agents read what a claims team would receive. The NTSB's
own 6 analysis files are withheld and, with the final report (HAR-07/02), form the **answer key**: 49 dated events,
19 parties and 13 relationships, each tied to pages in the input files. 14 of the events are *held out*: never looked
at while the system was improved.

## Results

Every agent uses the same model, `google/gemini-3.8-flash` through OpenRouter. The baseline is that model given all
pages in one prompt.

| | Team run `v2-full-2` | Earlier team run `v2-full-1` | One prompt, same model |
|---|---|---|---|
| Key events found, development set | **32 / 35** | 28 / 35 | 14 / 35 |
| Key events found, held-out set | **14 / 14** | 12 / 14 | 4 / 14 |
| Parties found | 18 / 19 | 18 / 19 | 7 / 19 |
| Relationships found | 3 / 13 | 3 / 13 | 0 / 13 |
| Claims kept by the verifier (refused) | 1,007 (5%) | 641 (11%) | 35 (35%) |
| Pages read | 1,721 / 1,737 | 1,519 / 1,737 | all, in one prompt |
| Time, model calls, cost | 26 min, 150 calls, $4.31 | 17 min, 99 calls, $3.10 | 1 call, $0.60 |

Every missed event is traced to where it was lost (page never read, read but not claimed, claim refused, different
date). In `v2-full-2`, two of the three misses came from the lead skipping one-page transmittals; the lead can no
longer skip documents ([decision 30](docs/DECISIONS.md)). The third is a date-range event.

**Weak spot:** relationships (3 of 13). The model links two companies, but the quote often doesn't show the link, so
the verifier refuses it.

`casefile score RUN_ID` recomputes any score from the run's records in MongoDB and `answer_key.yaml`.

## How it works

Four stages. Only the second uses agents.

1. **Ingest (once).** Reducto reads the text of every page (scans included) and splits each PDF into its documents. A
   model labels each document's type, date, author and recipient; a label is kept only if its exact words are on the
   page. Everything goes into MongoDB Atlas.
2. **The team run.** Agents organised the way a liability claim is worked:
   - **Claim professional (the lead)** owns the file. It sees only the document list and counts, never page text. It
     assigns work, approves the engineer, rules disputes, and closes the file.
   - **Defense counsel** (the insurer's lawyer) works out the parties and who agreed to what.
   - **Forensic engineer** (the technical expert) works out the technical record. It cannot start until the lead
     approves it, as with a real expert.
   - **Readers** are short-lived helpers that read a batch of pages and return claims, each with an exact quote.
   - **Agents never call each other.** They post typed events to an event log in MongoDB; a code dispatcher turns
     events into tasks, runs them in parallel, and holds a task until what it waits for exists.
   - **The verifier (code, no model)** checks every quote against the page, letter for letter, and that names and
     dates appear in the quotes. Failed claims are refused with a reason, never softened; each gets one automatic
     repair attempt.
   - **Guards:** token budget, task deadlines, a stall detector that wakes the lead, and a close check in code: the
     file can close only when every document has been read and nothing is open.
3. **Assembly (code).** Verified claims become the chronology, party map, exhibit list, absences and reading report.
4. **Scoring and export.** Compared against the answer key and exported for the UI.

## Where MongoDB does the work

| Collection | Role |
|---|---|
| `events` | The team's append-only event log, ordered and linked cause-to-effect; change streams wake consumers |
| `tasks`, `reservations` | Work items with waits-for and deadlines; a unique index ensures no two tasks of a role read the same document |
| `coverage`, `findings`, `refusals` | Which pages each reader was given, verified claims, refused claims with reasons |
| `model_calls` | Every call: who, which task, tokens, cost, the decision and the model's reasoning summary |
| `checkpoints` | LangGraph state of each role's task (plan, read, review, close), so a task can resume |
| `pages`, `documents`, `metadata`, GridFS `sources` | The ingested claim file; Atlas Search on page text is used to test absences |
| `cache` | Model and parser answers, so a finished run replays for free |

No agent keeps the run in its prompt. Each agent's context is rebuilt from MongoDB for every task, so the lead's
prompt stays between about 2k and 10k tokens however many pages have been read.

## The UI

A static Next.js app over the exported run (`web/`):

| Tab | Shows |
|---|---|
| **Board** | The chronology on a timeline, one lane per company; click any card to see the quote highlighted on the page image |
| **Chronology**, **Parties** | The deliverables as tables, each line openable to its evidence |
| **Trajectory** | The run as it happened: the process stage by stage, a timeline of every task, reader and event, and each agent's reasoning and decision |
| **Harness** | The team as the code defines it: roles, event catalogue, verifier rules, guards |
| **Memory** | What the run wrote to MongoDB, reading coverage, how the lead's context stayed bounded, refusals and absences |
| **Evaluation** | Scores against the answer key and the one-prompt baseline |

## Run it

```bash
cp .env.example .env            # ATLAS_CONNECTION_STRING, OPENROUTER_API (and REDUCTO_API_KEY, GEMINI_* for ingest)
uv sync
uv run casefile ping            # checks the Atlas connection

uv run casefile team --run-id my-run --allow-spend --fresh   # a full team run (~$4-5)
uv run casefile score my-run --missed                        # score against the answer key
uv run casefile export my-run --baseline baseline-1          # write the UI bundle

cd web && npm install && CASEFILE_RUN=my-run npm run dev     # open http://localhost:3000
```

Everything already paid for (parsed pages, metadata, model answers, source PDFs) is in the team Atlas cluster and the
committed caches; ingest refuses to spend unless run with `--allow-spend`. Tests: `uv run pytest` (unit) and
`uv run pytest -m integration` (against Atlas).

## Honest limits

- One case. The harness has no case-specific logic (the docket is a case configuration, a source adapter, the UI's source link and the CLI's
  default case id), but only this case has been run and scored.
- Relationships are weak (3 of 13).
- The answer key is ours, built from the NTSB report and audited against the input files independently of any run;
  every run is scored against the same key.
- Reasoning shown in the UI is the model provider's summary of its reasoning, not the raw reasoning tokens.

## Repository

- `src/casefile/ingest`: parsing, splitting, metadata with exact-span checks
- `src/casefile/verify`: the verifier (exact quotes, fields, absences)
- `src/casefile/team`: events, dispatcher, lead, counsel, engineer, readers, records desk, runner
- `src/casefile/evaluation`: answer key, scoring, baseline
- `src/casefile/export`, `web/`: the UI bundle and app
- `docs/DECISIONS.md`: every decision with its evidence; `docs/06-harness-v2.md`: the team design and what each run
  taught us
