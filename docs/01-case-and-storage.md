# Steps 1 and 2: the case, the answer key, and storage

Status: plan for approval, 2026-09-26. Nothing here is built yet.

## Step 1: the case

### What the docket contains (measured)

The docket HWY06MH024 has 94 files, 1,957 pages. By title, they fall into two groups:

| Group | Files | Examples |
|---|---|---|
| **Project records, 1997–2001** (made during the project) | 36 files, 370 pages | Design Policy Memorandum 107 (1997), contract general provisions, design spec 723.480, Gannett Fleming letters on the anchor system and factor of safety (1997–98), MassHighway fax on proof-test loads (1998), the value-engineering proposal and its rejection (1999), submittal transmittals 723.480-008A/D, -009B, -014C, -016A, Modern Continental's 7 Oct 1999 letter on anchor "tensile movement" and the letters that followed, the repair procedure (2000), Deficiency Report No. 1 closure (2001), the contract modification (2001), field engineer daily report excerpts, manufacturer literature |
| **Investigation material, 2006–07** (made after the collapse) | 58 files, ~1,590 pages | NTSB group chairman factual reports, interview transcripts, lab and FHWA test reports, photos, the police crash report, product certificates pulled in 2006 |

One file is not yet placed: the Inspector General's review of anchor bolts on contract C05B1 (file 58).
Its date needs checking.

### Proposal: the agent investigates the project records only

In a real claim, no NTSB report exists yet. The examiner has the project records. And the NTSB group
chairman factual reports already narrate the chain, so an agent that can read them would copy a
chronology rather than reconstruct one.

- **Case inputs** = the 35 project-record files, unaltered. File 58 (Inspector General review) stays withheld until its date is checked.
- **Withheld by design** = the 58 investigation files. The coverage report lists them as withheld, so
  nothing claims to have read them.
- **Answer key** = built from NTSB HAR-07/02 and the factual reports, which the agent never sees.

The honest consequence: 370 pages is about 230k characters of text layer plus OCR of the scans, well
within one Gemini prompt. The case does not demonstrate scale. What it can demonstrate is a checked
chronology, negatives backed by coverage, and a record of what was and was not read. The single-prompt
baseline stays in the eval, and the fleet must beat it or be cut.

### Answer key

A file `eval/answer_key.yaml`, written before any agent runs:
- **Events**: date, what happened, which case document shows it, and a short quote from that document.
  Each event also cites the HAR-07/02 page that establishes it, so the key is traceable to NTSB, not
  to us.
- **Negatives**: statements that must be reported as absent, each with the documents that must have
  been read to say so.
- **Party map**: the parties, their roles, and the relationships between them, which together form
  the project hierarchy. Roles include owner, management consultant, designer, contractor, supplier
  and inspector. Relationships include "contracted with", "reviewed submittals for" and "supplied
  to". The NTSB report's parties table (HAR-07/02 p. vii) is the reference. People appear by role
  where the docket redacts their names.
- **Split**: events are divided into a development set (used while building) and a held-out set
  (scored only at the end), so the harness is not tuned to the questions it is graded on.
- **Check**: every quote in the key must exact-match the ingested text. Any that fail show where OCR
  broke a quote, which feeds the OCR decision.

I draft the key from the report with page citations; you review it.

### Party map as an output

The examiner already maps the parties first; Step 0's journey step 2 is "map relationships: designers,
GC, prime and lower-tier subcontractors". So Casefile produces a party map alongside the chronology:
- Each party has a name, a type (organisation or person) and a role on this project.
- Each relationship links two parties with a type, a date range where known, and a citation
  `(document_id, quote)`. The citation is checked by the same exact-quote verifier. Letterheads, cc
  lines and transmittal "from/to" blocks are where these usually appear.
- A relationship with no citation is not shown.
- In the UI the map is the project hierarchy, and clicking a party filters the chronology to the
  events it took part in.
- It is scored against the answer key's party map: parties found, relationships found, and
  relationships asserted that are not in the key.

### Reference library (system level, separate from the case)

Starts with public texts only:
- Massachusetts repose statute (M.G.L. c.260 §2B);
- NAIC Model 902 deadlines;
- 49 U.S.C. §1154(b) and 49 CFR 831.4 (the limits on using NTSB reports);
- FHWA adhesive anchor technical advisory T 5140.30.

ASTM E488, E1512, E1188, E620 and E3176 enter as catalogue entries (title, scope, link) that cannot be
quoted, because their texts are paywalled.

The project's own contract documents (spec 723.480, general provisions) belong to the **case**, not
the library. They are evidence of what this project required.

## Step 2: storage

### Database

Run MongoDB locally in Docker with the `mongodb/mongodb-atlas-local` image rather than Homebrew
`mongod`. It supports Atlas Search and Vector Search, so search code is tested locally and not first on
migration day. Docker is running on this machine.

### What goes where

- **Raw files** stay on disk under `data/cases/<case_id>/raw/`, fetched by a script from the NTSB URLs
  with their SHA-256 and retrieval date. They are not committed: the repo stays small and anyone can
  re-fetch them.
- **Mongo** holds the documents' text, pages and character offsets, the manifest, and later the run
  state and memory.
- **Case and library are separate.** Case collections are written only by ingestion. Library collections
  are written only by a library management script, with versions and effective dates. No agent can
  write to either.

The full collection design is part of the ingestion step. Search and vector indexes are only added if
the ingestion ablation shows they help.

## Needs your approval

1. The agent reads only the 36 project-record files; the investigation material is withheld and used
   for the answer key.
2. The answer key: format, the development/held-out split, and my drafting it for your review.
3. The first contents of the reference library.
4. `mongodb-atlas-local` in Docker; raw files on disk, fetched by script, not committed.
