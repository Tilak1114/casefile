# Decisions

Approved decisions, newest last. Each links to where it was argued. Open questions are at the end.

| # | Date | Decision | Basis |
|---|---|---|---|
| 1 | 2026-09-26 | MongoDB runs locally while building; migrate to the event's stack once everything works | User instruction |
| 2 | 2026-09-26 | The demo shows a precomputed run, not a live agent. The UI shows the harness's work: the reconstructed chain, how the harness is set up, how it manages memory | User instruction |
| 3 | 2026-09-26 | Work step by step: a plan per step, approved before building; ambiguous choices settled by isolated tests or ablations | User instruction |
| 4 | 2026-09-26 | Case: the real NTSB docket HWY06MH024 (Big Dig ceiling collapse), unaltered. Answer key from NTSB HAR-07/02, used for the eval and as context only, never as a fault finding (49 U.S.C. §1154(b)) | Option A over a synthetic case |
| 5 | 2026-09-26 | Step 0 approved; end user is the liability-side claims examiner and defense counsel; outputs are a chronology, a cast list, an exhibit list, and a coverage report | [00-process-today.md](00-process-today.md) |
| 6 | 2026-09-26 | Gemini is the only LLM for agents and reasoning. External document-processing vendors may be used at ingestion if they measure better | User instruction |
| 7 | 2026-09-26 | Case inputs and the reference library are separate corpora. Case inputs, including the project's own contracts and specs, arrive per case and are never altered. The reference library (standards, statutes, the firm's playbook and guidelines) is managed at the system level, versioned, and updated independently of any case. Agents cite both through the same exact-quote verifier | User instruction |
| 8 | 2026-09-26 | Casefile outputs a party map (parties, roles, cited relationships, the project hierarchy) alongside the chronology; scored against the answer key | User instruction; Step 0 journey step 2 |
| 9 | 2026-09-26 | Everything crossing a boundary in the harness is a typed Pydantic model; model outputs are validated into them or rejected | User instruction |
| 10 | 2026-09-26 | Storage: `mongodb-atlas-local` in Docker (docker-compose.yml); raw docket files fetched by `casefile fetch` to `data/cases/<id>/raw/` with SHA-256, not committed; Atlas string kept as `ATLAS_CONNECTION_STRING` for migration | [01-case-and-storage.md](01-case-and-storage.md) |
| 11 | 2026-09-26 | The main UI is an investigation board: a navigable canvas of documents, events and parties with the connections between them drawn as a graph. Every connection is backed by a verified citation | User instruction |
| 12 | 2026-09-26 | Ingestion text: born-digital pages use the PDF text layer; scanned pages use Reducto r-1. Figure blocks are dropped from the block list (its filter only cleans chunk text); inline tags are stripped with offsets kept; scan text is labelled OCR and every citation shows the page image, because all readers silently corrected some text ("submitt" to "submit") | 25-page test: on the 18 contested lines the user adjudicated, Reducto 14/18, Gemini 8/18, Extend 3/18. Partial review; the user judged further adjudication not worth it now |
| 13 | 2026-09-26 | The agent reads only the project records made during the project (36 files, 370 pages). The 58 files created by the investigation after the collapse are withheld, listed as withheld in coverage, and used to build the answer key | [01-case-and-storage.md](01-case-and-storage.md) |
| 14 | 2026-09-26 | Ingestion is Reducto only: r-1 parse on every page, Reducto Split for logical documents (general taxonomy, partition by each document's own identity). No hybrid text-layer routing; that is a later improvement. Supersedes the earlier dual-source plan | User instruction; [02-ingestion.md](02-ingestion.md) |
| 15 | 2026-09-26 | Production labels (slip sheets, cover sheets, dividers added when documents were assembled) and producer-supplied file names are hidden from the agent and never citable; shown in the UI as labels | [02-ingestion.md](02-ingestion.md) |
| 16 | 2026-09-26 | Classification and metadata by Gemini into typed models; every field must carry an exact-matching span or stay empty | [02-ingestion.md](02-ingestion.md) |
| 17 | 2026-09-26 | Design for any case file, not the demo docket; simplest general component first. The text-layer library comparison was run (pypdfium2 ≈ PyMuPDF; pdfplumber worse) and is kept for the later born-digital improvement | User instruction |
| 18 | 2026-09-26 | Verifier: quotes must exact-match stored text after whitespace and quote/dash folding only; asserted fields must match span-checked metadata or the claim is refused; negatives need full-text read coverage of every in-scope document, undated ones included; search-only coverage never supports a negative | [03-verifier.md](03-verifier.md) |
| 19 | 2026-09-26 | Submit against Statement Two (long-horizon): the goal is complete coverage with every claim verified; refusals and unread pages are the hard signals the loop works from; memory is verified findings and coverage in MongoDB. No self-modifying harness today; a self-evolving or learning layer is planned for later. Continue on local Mongo until the Atlas sandbox string arrives | User instruction |

## Open


- Document classification and splitting at ingestion: taxonomy, and which classifier (Gemini, Extend,
  Reducto), chosen on a hand-labelled sample. Jev deferred by the user on 2026-09-26.
- Fleet: orchestrator plus subagents via a `delegate` tool, with a concurrency cap and spawn budget;
  must beat a single-prompt whole-docket baseline on the answer key.
- The firm playbook in the reference library is authored by us from Step 0's sourced process and
  labelled synthetic; its contents still to be planned.
