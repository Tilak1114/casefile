# Harness v2: an event-driven claims team

Terms: the **claim file** is the whole package the team works on (88 source PDFs); a **source PDF** is
one of the 94 numbered PDFs in the NTSB docket; a **document** is one original letter, report or form
inside a PDF (found by Reducto Split).

Status: approved 2026-09-26; building. Grounded in `00b-claims-team.md` (sourced
roles and sequence) and in what run `full-1` showed.

## What v1 taught us (measured)

- One examiner deciding one action per turn is a bottleneck: 11 of 27 turns went on repairs, coverage grew
  a few documents at a time, and the run reached 421 of 1,737 pages before an Atlas failover stopped it.
- Reading every page with a model is the wrong goal. All project correspondence (letters, memos,
  submittals, procedures, deficiency reports) was read; the unread ~1,300 pages are mostly bulk test data
  (the FHWA reports alone are 563 pages).
- The verifier works: 7% of the harness's claims were refused against 35% of the single prompt's.
- Relationships were weak (2 of 13), and absences were never reached.

## The team (liability side, document-only claim file)

Only roles the sources place on the liability side, and only those this claim file gives work to.

| Role in Casefile | Real role | Owns | Produces | Authority |
|---|---|---|---|---|
| **Claim professional** (lead) | the carrier's claim professional / handler | the claim file: opens it, assigns counsel, approves expert retention, convenes roundtables, rules disputes about meaning, closes the claim file | assignment letters, approvals, rulings, the case brief | final say inside the claim file; never states fault or coverage (no policy is in the claim file) |
| **Defense counsel** | panel counsel | who the parties are, how they are related, who was responsible for what under the contracts and approvals; "outbound risk transfer opportunities" stated as documented responsibilities, not fault | initial assessment, status reports, party map claims, requests for expert retention | its own judgment on what matters; needs the lead's approval to retain the engineer |
| **Forensic engineer** | expert retained by counsel | the technical record: requirements, submittals and dispositions, tests and results, deviations, what the record does not contain | technical findings and absences, answers to requests | none; states documented facts, never causes |
| **Readers** (workers) | the reading a person does | read whole documents for a role, return quoted claims | claims | none |

Left out, with the reason recorded: coverage counsel (no policy in the claim file), cost expert (no repair
estimate), forensic accountant (no economic damages), and every property-side role.

## Team members in detail

Each agent is specified the same way: who it mirrors, what wakes it, what it waits for, what it sees, what
it can do, what it publishes, when it is done, and what it may never do.

### Claim professional (lead) · model
- **Mirrors**: the carrier's claim professional (NAIC ch.18; CLM; Hartford CD guidelines).
- **Job**: owns the claim file. Assigns counsel; approves or declines expert retention with a scope; marks
  documents out of scope with a reason; handles expired tasks; convenes a roundtable and rules disputes
  about meaning; decides the claim file is complete; writes the case brief from verified claims only.
- **Wakes on**: `claim_file.opened`, `expert.requested`, `report.submitted`, `dispute.opened` (meaning),
  `position.submitted`, `task.expired`, `guard.hit`.
- **Waits for**: nothing to start; a ruling waits for both `position.submitted`; closing waits for no open
  requests, disputes or tasks and every document read or excluded.
- **Sees**: the document index (type, date, author, recipient, pages, who read it), coverage, headline
  counts of verified and refused claims, open requests, disputes and tasks, reports received. Never page text.
- **Can**: assign work, approve or decline the expert, exclude documents with a reason, rule a dispute
  (must cite claim ids), close the claim file, submit the brief.
- **Publishes**: `counsel.assigned`, `expert.approved` / `expert.declined`, `work.assigned`, `scope.excluded`,
  `dispute.ruled`, `claim_file.closed`, `brief.submitted`.
- **Never**: reads pages, makes claims about their content, states fault or coverage.

### Defense counsel · model
- **Mirrors**: panel defense counsel (Hartford CD guidelines; DRI; JSH).
- **Job**: the parties and contractor tiers; how they are related (contracted with, represented, reviewed
  submittals for, supplied, inspected for); names written differently; who approved or was responsible for
  what, as documented (the guidelines' "outbound risk transfer opportunities", stated as facts, not fault);
  asks for an expert when a question is technical; answers requests about parties and approvals; reports an
  initial assessment and status; proposes absences in its scope.
- **Wakes on**: `counsel.assigned`, `work.assigned`, `request.raised` (to counsel), `expert.declined`,
  `dispute.ruled`.
- **Waits for**: nothing to start; its initial assessment waits for its first reading pass.
- **Sees**: the index of its assigned documents, their text only through its readers, its own verified
  claims, the party map so far.
- **Can**: start readers on documents with a focus, search, request an expert with a scope, raise and answer
  requests, open a dispute, submit a position, submit a report, propose an absence.
- **Publishes**: `expert.requested`, `request.raised` / `request.answered`, `dispute.opened`,
  `position.submitted`, `report.submitted`, `absence.proposed`.
- **Never**: retains the engineer without approval; states fault.

### Forensic engineer · model
- **Mirrors**: the expert counsel retains with the carrier's approval (CLM; Thompson Coe; Hartford).
- **Job**: the technical record: design requirements and values (factor of safety, proof loads),
  submittals and how they were dispositioned, test methods and results, deviations, repairs; absences such
  as a test that was never run; answers technical requests; reports.
- **Wakes on**: `expert.approved` (first task), `work.assigned`, `request.raised` (to engineer),
  `dispute.ruled`.
- **Waits for**: `expert.approved`. It cannot start before. The lead approves it when counsel asks, or on its
  own initiative when the index shows technical material (added after smoke-2, where counsel never asked and
  the lab and test reports went to counsel with a legal focus).
- **Sees**: as counsel, for its own documents and claims.
- **Can**: as counsel, except requesting an expert.
- **Publishes**: `request.raised` / `request.answered`, `dispute.opened`, `position.submitted`,
  `report.submitted`, `absence.proposed`.
- **Never**: gives an opinion on cause.

### Readers · model, started on the go
- Started by counsel or the engineer with a batch of whole documents (about 25 pages) and a focus. Returns
  dated events, parties, relationships, aliases and open questions, each quoted with its page.
- Sees its documents' text, the role's brief and the focus. Has narrow retrieval only (`find_references`,
  `search_text`, `get_document`, about two extra documents) to resolve a reference on the spot.
- The system logs the pages as read before the model runs. A refused claim is retried once, automatically,
  with the page text and the reason.
- At most 4 model calls run at once across the team.

### Code components
- **Dispatcher**: turns events into tasks, starts a task when its `waits_for` are met, enforces the cap,
  deadlines and guards, records processed event ids.
- **Verifier**: checks every claim (`claim.verified` / `claim.refused`), rules disputes about what a page says,
  tests proposed absences against coverage and search.
- **Assembly**: on `claim_file.closed`, builds the chronology, party map, exhibits and coverage report.

## Retrieval: the records desk

Retrieval is a lookup, not a judgement, so it is deterministic code exposed as typed, read-only tools; the
agents decide what to look up. No separate retrieval agent. Every tool hides production labels and withheld
PDFs and writes coverage automatically. Agents never get raw database queries (the MongoDB MCP server is
for developers only), because that would bypass coverage logging, label hiding and typed results.

| Tool | Takes | Returns | Who may use it | Coverage written | Status |
|---|---|---|---|---|---|
| `list_documents` | type, date range, author, recipient, source PDF | the structured index (Reducto split + span-checked metadata) | counsel, engineer, lead | — | data built; tool planned |
| `get_document / get_pages` | document or page ids | full page text | counsel, engineer; readers (capped) | read | built inside readers; tool planned |
| `search_text` | query, filters, phrase or not | Atlas Search keyword and phrase results with highlights | counsel, engineer; readers (capped) | search | built |
| `find_references` | a document | reference numbers it cites (letter C09B2-xxxx, submittal 723.480-xxx, DR No. 1), resolved to the documents carrying them; deterministic pattern matching | counsel, engineer, readers | — | planned (also draws the Board's reply lines) |
| `get_claims / get_party` | filters, a name | the team's verified findings and the party map so far | counsel, engineer; lead (counts and headlines only) | — | data built; tool planned |
| `coverage_status` | a scope | what is indexed, read (by whom, with what focus), excluded or unread | all roles | — | data built; tool planned |
| `search_semantic` | query, filters | Atlas Vector Search over page embeddings (Voyage or Atlas automated embeddings) | counsel, engineer | search | proposed; only if a retrieval test shows it finds answer-key evidence that keyword search misses |

Readers get narrow retrieval (about 2 extra documents per reader, to resolve a reference such as "see our
letter of 12 October" on the spot); anything bigger goes back to the role as an open question. A referenced
document is attached only if it is 30 pages or fewer and the reader's role can reserve it, so no other task of
the role has read or is reading it (smoke-2 gave readers 1,435 pages of which 745 were distinct, because
parallel readers attached the same long reports). Counsel and
the engineer get the full set. The lead gets metadata and counts only, so it never sees page text.

## Keeping context from thinning up the hierarchy

Every layer can only pass up what the layer below noticed. Measured on run full-1, the 22 missed
answer-key events were lost here:

| Where it was lost | Missed | What it means |
|---|---|---|
| Evidence page never read | 13 | most in the daily-report printout (PDF 019, 8 events) and the post-collapse test and lab reports |
| Read, but no claim made | 1 | the reader-level loss: E22, Powers reporting 120 ft-lb torque above the 50–90 range |
| Read, claim made, refused by the verifier | 5 | found, but the quote or date did not check out; v2's automatic repair targets this |
| Read, claim verified with a different date | 3 | found, but dated by another event on the same page |

The dominant loss is what nobody read, not what readers dropped. v2 addresses both:

1. **Claims are pointers, not summaries.** Every claim carries its source PDF, page and exact quote; any role can open the full document at any time. What travels up is a reference, not a retelling.
2. **Gaps are visible.** Coverage records who read each page and with what focus, so the lead can see what nobody has looked at through, say, a technical lens.
3. **Deliberate overlap.** Key document types (correspondence, submittals, deficiency reports) are read by both roles with their own focus. In full-1 no document was read by both. The one-reviewer ablation measures whether the overlap earns its cost.
4. **Roles can read for themselves.** Counsel and the engineer can read a high-value document directly, not only through readers.
5. **Loose ends travel as events.** Open questions and unresolved references are published as events the roles must act on.
6. **Loss attribution in every evaluation.** Each missed answer-key event is attributed to where it was lost: never read, read but not claimed, claimed but refused, or a different date.

## Communication: events, not calls

Every interaction is an event in an append-only `events` collection in MongoDB. Components never call each
other; they react to events through **MongoDB change streams**, like people reacting to letters, requests
and reports in an office.

### Event record (typed)

`id`, `case_id`, `run_id`, `type`, `from` (role or component), `to` (role, or none for broadcast),
`subject` (claim, document or task ids), `correlation_id` (the conversation it belongs to), `causation_id`
(the event that caused it), `payload` (a typed model per event type), `at`.

### Event catalogue

| Event | From → to | Mirrors |
|---|---|---|
| `claim_file.opened` | system → lead | claim assigned |
| `counsel.assigned` | lead → counsel | handler assigns defense counsel |
| `expert.requested` | counsel → lead | counsel asks prior written approval to retain an expert |
| `expert.approved` / `expert.declined` | lead → counsel, engineer | approval with scope |
| `work.assigned` | lead or counsel → role | assignment letter with documents and focus |
| `reader.started` / `reader.finished` | role → system | a document read in full (coverage written by the system) |
| `claim.verified` / `claim.refused` | verifier → the claim's role | the check against the page |
| `claim.repaired` | reader → verifier | the one automatic retry of a refused claim |
| `request.raised` / `request.answered` | any role → any role | a request for information between team members |
| `report.submitted` | counsel, engineer → lead | initial assessment, status report |
| `dispute.opened` | any role → verifier or lead | disagreement over a claim |
| `position.submitted` | disputing roles → lead | each side's case, with citations |
| `dispute.ruled` | verifier or lead → all | the ruling, with citations |
| `absence.proposed` / `absence.checked` | role → verifier | a negative, tested against coverage and search |
| `task.expired` | system → lead | a request or assignment passed its deadline |
| `claim_file.closed` | lead → system | the lead closes the claim file; assembly runs |

## Independence and dependencies

- **Each role is its own LangGraph agent** with its own checkpointed thread. It wakes when an event
  addressed to it arrives, works its task, publishes events and goes back to waiting. Roles run in
  parallel; nothing waits on anything it does not need.
- **Dependencies are declared, not improvised.** Each role's spec lists the events it consumes and
  produces, and each task can carry `waits_for`: the events that must exist before it is ready. Examples:
  - the engineer cannot start until `expert.approved` (the real sequence);
  - counsel's status report waits for the engineer's `report.submitted` when it asked the engineer a question;
  - the lead cannot close the claim file while any request or dispute is open, or any relevant document unread.
- **A deterministic dispatcher** turns events into tasks (`pending → ready → running → done | expired`),
  starts a task only when its `waits_for` are met, and enforces the cap on model calls running at once.
  Nothing polls or busy-waits.
- **Delivery is at least once, handled idempotently:** every consumer records the event ids it has
  processed, so a crash (like full-1's) resumes from checkpoints without doing work twice.
- **Deadlines** are counted in dispatcher cycles and budget, not wall-clock time. An expired task becomes a
  `task.expired` event the lead must handle.

## Collaboration and disputes

- **Requests**: any role can ask another for information (`request.raised`), for example the engineer asking
  counsel which party approved a submittal. The answer (`request.answered`) must cite verified claims, or
  report "not found" with the coverage searched.
- **Disputes** are raised when one role's claim conflicts with another's (a different date for the same
  event, two documents that disagree, a relationship the other role's evidence contradicts):
  - **about what a page says**: the verifier rechecks deterministically and rules;
  - **about what it means**: the lead convenes a roundtable. Each side submits a position with citations,
    and the lead rules, citing evidence. Both positions stay on the record and appear in the UI.
  How carriers resolve disagreements between their own experts is unsourced, so the lead's ruling is our
  design choice, and the UI shows it as such.

## Coverage in two levels

- **Indexed**: every document, from ingestion (type, date, author, recipient, page count) and search. Free
  and complete.
- **Read in full**: pages a reader was given. A role reads what its task needs; the lead may mark documents
  out of scope with a stated reason (for example bulk test data), and that decision is on the record.
- Absences may only be claimed over scope that was read in full, and must survive the search check.
- The claim file closes when every document is either read in full by some role or marked out of scope with a
  reason.

## Memory (MongoDB)

Existing: pages, documents, metadata, coverage, findings, refusals, workers, outputs, cache, checkpoints.
New: `events` (the log, source of truth for what happened), `tasks` (dispatcher state), `disputes`,
`requests`, `reports`, `subscriptions` (each consumer's processed ids and change-stream resume token).

## Models

- All model calls go through OpenRouter (key `OPENROUTER_API` in `.env`), through one cached, typed client
  with the spend guard.
- Every agent uses `google/gemini-3.8-flash` to start: the model the baseline and run full-1 used, so the
  comparison is fair (user, 2026-09-26).
- Measured on three documents (same prompt and verifier), for a later cost pass:

| Model | $ in / out per M | Verified / claims | Refused |
|---|---|---|---|
| gemini-3.8-flash | 0.75 / 3.75 | 21 / 23 | 9% |
| gemini-2.5-flash | 0.30 / 2.50 | 57 / 85 | 33% (events 28/30, relationships 6/24, aliases 0/6) |
| gemini-3.1-flash-lite | 0.25 / 1.50 | 12 / 19 | 37% |
| gemini-2.5-flash-lite | 0.10 / 0.40 | 38 / 64 | 41% (relationships and aliases mostly refused) |

## Guards

Rules the harness enforces in code; hitting one is an event and the lead is told. Built = exists in v1;
planned = part of v2; proposed = for the user to accept or drop. Pauses for a human are not included.

| Kind | Guard | Status |
|---|---|---|
| Budget | Tokens per run | built |
| Budget | Readers started per run | built |
| Budget | Turns / dispatcher cycles per run | built |
| Budget | Dollar cap per run, from the cost OpenRouter reports on every call | proposed |
| Budget | No paid call without `--allow-spend`; cached answers replay free | built |
| Concurrency | At most 4 model calls at once across the team | built |
| Concurrency | Back off and retry when the provider rate-limits | proposed |
| Progress | Stop after N cycles with no new verified claim, coverage or ruling | built |
| Progress | Detect a role repeating the same action (a loop) | proposed |
| Progress | Deadlines on tasks and requests; expiry is an event the lead handles | planned |
| Progress | Reject a `waits_for` that can never be met (an event nobody can send, or a cycle) | planned |
| Progress | Limit rounds per dispute and depth of requests between roles | planned |
| Authority | Each role may publish only the events in its spec; the dispatcher refuses the rest | planned |
| Authority | The engineer cannot start before `expert.approved` | planned |
| Authority | Readers get only narrow retrieval (about two extra documents); no agent can write the case index | planned |
| Context | The lead never sees page text; no agent sees file names, production labels or withheld PDFs | built |
| Context | A size cap on every prompt | proposed |
| Output | Every model output parsed into a typed model or rejected | built |
| Output | Every claim checked against its page: quote, dates, names | built |
| Output | One automatic repair per refused claim | planned |
| Output | Flag claims that use fault or cause language (liable, negligent, at fault, caused) for the lead | proposed |
| Output | Answers and rulings must cite verified claims | planned |
| Evidence | Absences only over pages read in full, and only if a search finds no counter-example | built |
| Evidence | Excluding a document requires a stated reason | planned |
| Integrity | Append-only event log; each event handled once in effect; resume from checkpoints | planned |
| Integrity | Restoring a snapshot refuses to overwrite a shared database without confirmation | built |

## Evaluation

- Same answer key (dev and held-out) and the same single-prompt baseline.
- v1 against v2 on found events, relationships, parties, refused rate, absences produced and verified,
  cost, and time.
- Ablations, each run in isolation: without disputes; without requests between roles; one reviewer
  instead of two; keyword search only vs keyword plus semantic search.
- Loss attribution for every missed answer-key event (never read / read, not claimed / refused / other date).
- Also fix before the run: Split returned overlapping partitions for source PDF 011 (pages counted twice).

## UI changes

- The Harness screen shows the team, the event catalogue and each role's subscriptions.
- The replay becomes the event stream: filter by role, follow a conversation by correlation id, open any
  dispute with both positions and the ruling.
- The process itself, shown intuitively (user request, 2026-09-26): open → lead assigns and retains the
  engineer → roles read through readers in parallel → verifier keeps or refuses each claim → reports → lead
  reassigns or excludes → disputes and requests → close check → absences → assembly. Each stage is drawn from
  the run's own events, with its counts (documents, pages, claims, refusals, cost), not a static diagram.

## Needs your approval

1. The team: claim professional (lead), defense counsel, forensic engineer, readers; and the roles left out.
2. Events through a MongoDB `events` collection and change streams, with the catalogue above.
3. Dependencies via declared `waits_for` and a deterministic dispatcher; at-least-once, idempotent.
4. Disputes: the verifier for what a page says, the lead's roundtable for what it means.
5. Two-level coverage, and the lead's power to mark documents out of scope with a reason.
6. Models: Gemini now; OpenRouter later.
7. The evaluation, including the ablations and loss attribution.
8. The records desk: typed retrieval tools, narrow for readers, full for roles, metadata only for the lead.
9. The six measures against context thinning up the hierarchy.

## After the first full run (v2-full-1)

Measured on v2-full-1 (closed by the lead, 17 min, $3.10): nothing was lost to coverage (0 of the missed events
were on unread pages); the losses moved to reading and verification. Three changes, each tested before building:

- **Readers are batched by characters (about 40k), and an over-long document is read in page windows.** Ablation
  on the daily-report printout (PDF 019, 9 key events) with a neutral focus: one call per document 33 events and
  8/9 key events; windows 53 and 9/9; windows plus a rule to report each dated log entry with its date line 73
  and 9/9, for about $0.40.
- **Names in quotes.** A name matches when only its formatting differs (case, punctuation, "Inc."), and at
  assembly a claim refused only because a party is named by a verified alias (B/PB) is reinstated with the alias
  claim recorded. On v2-full-1's 39 name refusals this rescues 13; most relationship refusals remain, because
  their quotes do not show the relation.
- **Hyphens at line breaks.** The verifier joins a word across a line-end hyphen, keeping or dropping the
  hyphen. On v2-full-1 this rescues 6 of 22 unfound quotes.

The answer key was also audited: for every event, the 88 input files were searched, independently of any run,
for other pages that document the same occurrence (mostly copies in PDF 093). 77 pages were added, every quote
matched by code; dates and splits are unchanged. All runs were re-scored against it.

The UI gained a Trajectory screen for team runs: the process stage by stage, a swimlane timeline of tasks,
readers and events read from the MongoDB event log, and a detail panel for each.

## After v2-full-2 started

- **Exclusion guard.** The lead may exclude only documents over 20 pages; shorter ones must be assigned. In
  v2-full-2 the lead excluded 12 one-page submittal transmittals as "standard cover sheets", yet 9 of those pages
  are answer-key evidence (review stamps and return dates for E04, E10, E33, E35, E38). Enforced in code, stated
  in the lead's prompt, and a refused exclusion is recorded in the lead's task note.
- **Reasoning capture.** Every model call now records the typed decision and the provider's reasoning summary
  (OpenRouter `reasoning`, Gemini's own summary, not raw tokens), tied to its task and, for readers, its worker.
  v2-full-1's decisions were backfilled from its cache files matched by name and write time (97 of 99; checked
  against the events they produced); it has no reasoning summaries. The Trajectory screen shows both.
- `casefile team --fresh` calls the model for every step instead of replaying cached answers.
