# Step 3: ingestion

Status: approved 2026-09-26 (revised to Reducto only). Ingestion is a fixed pipeline, not an agent,
and it must work for any case file, not just the demo docket. Simple first; hybrids and optimisations
are later improvements.

## Pipeline

1. **Receive files.** Raw files for a case, each with its SHA-256 and source. (For the demo, `casefile
   fetch` downloads the public docket.)
2. **Parse** each file with Reducto r-1 (`return_ocr_data` on for word boxes). Keep the job id. Raw
   responses are cached on disk keyed by file hash and settings, so nothing is paid for twice.
3. **Split** each file into logical documents with Reducto Split on the parse job (`jobid://`, so no
   re-parse). One general taxonomy of document types for construction records, each with
   `partition_key` = the document's own identity (its reference number, or its date and sender), so a
   bundle of many letters comes back as one partition per letter. Split's `high`/`low` confidence is
   kept; `low` is flagged for review.
4. **Clean** page text: drop Figure blocks (model-written descriptions), strip inline tags with an
   offset map back to Reducto's output, record what was stripped. Stored text keeps the original
   characters; any quote or dash folding happens only inside the verifier.
5. **Production labels.** Pages added by whoever assembled the production (slip sheets, cover sheets,
   exhibit dividers) are a document type of their own. They are shown in the UI as labels, never given
   to the agent and never citable. File names supplied by the producer are treated the same way.
6. **Metadata** per logical document: type (from Split), date, author organisation, recipient
   organisation, filled by Gemini into a typed model. Every field carries a span of the document's
   text that exact-matches, or stays empty.
7. **Store** in Mongo: `files`, `pages`, `documents`, `ingest_runs` (costs, timings, failures).
8. **Index** with Atlas Search. Vector search only if a retrieval test shows keyword search misses
   evidence.

## Document types (split taxonomy)

letter, memorandum, e-mail, fax transmittal, submittal transmittal, request for information, change
order or contract modification, meeting minutes, daily report, inspection or test report, deficiency
or nonconformance report, specification or contract provisions, drawing, product literature, procedure
or method statement, production label (slip sheet or cover sheet added when the documents were
assembled), other.

## Typed models (Pydantic)

`ReductoParse`, `ReductoSplit`, `PageText` (text, stripped markup, block boxes), `LogicalDocument`,
`DocumentMetadata` (each field with its source span), `IngestRun`.

## Tests

- Unit, with recorded Reducto responses: tag stripping keeps offsets; figure blocks dropped; split
  partitions become documents; production labels are excluded from agent text; cache keys; metadata
  spans must exact-match.
- Check after the run: every answer-key quote exact-matches the stored text of its page.

## First run (2026-09-26)

- 36 files, 370 pages, 0 failures, 87 s wall time, 8 files at a time.
- 56 production-label pages found, including every NTSB cover sheet and divider, after the label
  description said that a page which only titles what follows is a label even when one document
  follows. The first wording missed 8 of 36 cover sheets.
- 106 content documents (32 letters, 17 product literature, 12 submittal transmittals, …); 45 of all
  147 split results carry Split's `low` confidence.
- All 82 answer-key evidence quotes exact-match the stored page text (one key quote was corrected
  against the page image: "Customer: Modern Continental Construction Co.").
- Known limitation: Split's granularity varies between runs. The same bundle came back once with
  enclosures as separate documents and once with enclosures inside their parent document.
- Reducto credits: 789 for the first run, 387 for the re-split, 105 for the label test.

## Later improvements (not built now)

- Use the PDF text layer on born-digital pages. The docket measurement found PyMuPDF and pypdfium2
  agree closely; pdfplumber reversed rotated text and merged words.
- Route pages by agreement between the text layer and OCR.

## Cost (list prices)

Parse $10 + word layer $2 per 1,000 pages; Split $20 per 1,000 pages with no extra parse. The 35
readable files (333 pages) come to about $10.
