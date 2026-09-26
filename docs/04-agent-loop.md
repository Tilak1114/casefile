# Step 5: the agent loop

Status: plan for approval, 2026-09-26. Statement Two (long-horizon): the run works toward a goal
measured by hard signals, and its memory lives in MongoDB, not in the prompt.

## Goal and hard signals

**Goal:** every readable document read, every claim verified, the chronology, party map, exhibit list
and coverage report produced.

**Signals the loop acts on** (all computed by code, never judged by the model):
- **coverage**: documents not yet read;
- **refusals**: claims the verifier refused, with its reasons;
- **open questions**: references a reader found but could not resolve (e.g. "letter mentions Deficiency
  Report No. 1"), which call for a search;
- **progress**: new verified findings or new coverage per turn.

The run ends when coverage is complete and nothing is pending, or when a guard stops it; either way the
coverage report lists what was not read.

## Shape: an organisation, not a pool of agents

The fleet mirrors how a claims team divides the work (Step 0). Each role has a standing
responsibility, its own context and its own tools. Mechanical steps are code, not agents. Any role can
start short-lived workers when it needs documents read.

```
load_state -> examiner decides -> validate -> roles act (spawning workers) -> verify -> record
           -> assemble (code) -> checkpoint -> (loop | finish)
```

### Roles (standing, Gemini)

| Role | Mirrors | Responsibility | Sees | Tools |
|---|---|---|---|---|
| **Claims examiner** (lead) | the claims professional who owns the claim and relies on experts (CLM) | plans the investigation, assigns work to the other roles, follows coverage gaps, refusals and open questions, decides when the file is done | the document list (type, date, author, recipient), coverage, verified findings, refusals, open questions; never page text or file names | `assign`, `search`, `finish` |
| **Parties reviewer** | defense counsel mapping parties and contractor tiers from the records, "not rely upon your insured" (JSH) | who the parties are, how they are related (contracted with, represented, reviewed submittals for, supplied), which names are the same party | the documents it is assigned, its own verified claims | `spawn_reader`, `read`, `search` |
| **Technical reviewer** | the forensic engineer's document review (ASTM E2128 step 1, E1188) | design requirements, submittals and their dispositions, tests and their results, deviations, and what the record does not contain; facts only, no causation opinions | the documents it is assigned, its own verified claims | `spawn_reader`, `read`, `search` |

A coverage-counsel role is left out: the case file has no policy documents for it to read.

### Workers (on the go, a capability)

- Any role can start a **reader** on a set of documents with a focus ("dates, parties and approvals"
  or "design values and test results"). A reader reads the whole documents and returns typed claims
  with `(page_id, quote)` citations and open questions. The harness, not the model, writes a READ
  coverage record for exactly the pages it was given.
- At most `MAX_WORKERS_ACTIVE = 4` run at once, within `MAX_WORKER_SPAWNS` per run. Workers cannot
  start other workers.

### Deterministic steps (code)

- **Verify**: every claim goes through the Step 4 verifier. Verified claims enter memory; refused ones
  go back to the role that made them, with reasons; each may be repaired once.
- **Party map**: assembled from verified party and relationship claims. Two names are merged only by
  a verified claim that quotes them as the same party (for example "Bechtel/Parsons Brinckerhoff
  (B/PB)"), never by guesswork.
- **Chronology**: verified event claims ordered by date; duplicates (same page, same date) merged.
- **Negatives**: roles propose what is absent; the verifier accepts one only if reads cover its scope.
- **Record and checkpoint**: findings, refusals, coverage and a trace event per step go to Mongo;
  LangGraph's MongoDB checkpointer saves the run so it can be stopped and resumed.

## Memory (all in MongoDB, typed)

| Collection | What | Used by |
|---|---|---|
| `findings` | verified claims: events, parties, relationships, negatives, with matches | outputs, UI, examiner context |
| `refusals` | refused claims and reasons | repair loop, UI |
| `coverage` | READ and SEARCH records (Step 4) | negatives, coverage report, examiner context |
| `trace` | one event per node: action, inputs and outputs in summary, tokens, time, context size | UI replay |
| checkpoints | LangGraph run state | resume |

The examiner's prompt is rebuilt from these each turn, so its size stays bounded however long the
run is; the trace records that size per turn so the UI can show it.

## Guards (constants, as in PerceptFlow)

- `MAX_TURNS = 40`, `MAX_WORKERS_ACTIVE = 4`, `MAX_WORKER_SPAWNS = 60`, `MAX_REPAIRS_PER_CLAIM = 1`,
  `MAX_UNPRODUCTIVE_TURNS = 3` (no new coverage and no new verified finding), and a token budget.
  Hitting one stops the run with the reason recorded.

## Outputs

- **Chronology**: verified events ordered by date, each line with its quote and page.
- **Party map**: parties, aliases and verified relationships.
- **Exhibit list**: every cited document with its source file SHA-256.
- **Coverage report**: what was read, what was only searched, what was never read, what was withheld
  by design.

## Evaluation

- Score against the answer key, dev and held-out separately:
  - an event is found if a verified claim cites a page the key event cites and its date matches at the
    key's precision;
  - parties by name or alias; relationships by party pair and type; negatives by statement and scope;
  - also: verified vs refused claims, coverage, tokens, cost, time.
- **Baseline**: one Gemini prompt with all readable page text, asked for the same typed output, run
  through the same verifier and scoring. The fleet stays only if it beats the baseline; otherwise the
  result is reported as is.

## Cost and sharing

- All Gemini calls go through the cached client, so a finished run replays for free and the snapshot
  carries the run for teammates. Paid calls need `--allow-spend`.
- Rough estimate, to be measured: readers read about 370 pages once, a few dollars per run.

## Build order (today)

1. Typed models: actions, findings, trace events, run state. Tests for validation and guards.
2. Tools: search (Atlas Search index on page text), read, and the coverage writes. Tests.
3. Reader worker and verifier wiring; run it on 3 documents and check the output by hand.
4. The two reviewer roles, then the examiner loop with the checkpointer and guards; a short run, then
   the full run.
5. Deterministic party map and chronology assembly.
6. Outputs, scoring, the baseline.

## Needs your approval

1. The loop, the typed actions, and that the claims examiner never sees page text.
2. The roles (claims examiner, parties reviewer, technical reviewer), readers as on-the-go workers
   with a cap of 4, and party map, chronology and negatives checks as code.
3. The guard values.
4. The evaluation, including the rule that the fleet must beat the single-prompt baseline.
