# Step 4: the verifier, coverage and document metadata

Status: built 2026-09-26. Tests were written before the implementation.

## Verifier (`src/casefile/verify/`)

- **Positive claims** cite `(page_id, quote)`. A claim is verified only if every quote is found on a
  readable page that is not a production label, and every typed field it asserts (date, author
  organisation, recipient organisation, document type) agrees with the cited document's metadata.
  - Matching collapses whitespace and folds curly quotes, dashes and non-breaking spaces. Case,
    spelling, punctuation and word order must match. Stored text is never changed; matches return
    offsets into the original text for highlighting.
  - A coarser date ("1999-10") of a known date ("1999-10-07") is accepted; anything else is refused.
  - An asserted field the document's metadata does not have is refused, not assumed.
  - One bad citation refuses the whole claim. Refused claims are not softened.
- **Uncited claims** are marked `interpretation` and are never shown as fact.
- **Negatives** state a scope (document types and an optional date window) and cite coverage records.
  They are verified only if full-text reads cover every page of every document in scope. Undated
  documents are always in scope. Search-only coverage never supports a negative. Refusals list the
  pages that were never read.

## Coverage (`verify/coverage.py`)

Every read or search in a run writes a `CoverageRecord` (mode, pages, query) to Mongo; negatives cite
them by id.

## Document metadata (`ingest/metadata.py`)

Gemini reads each non-label document and proposes its date, author organisation and recipient
organisation, each with the exact span and page it came from. A field is kept only if its span is on
that page and its value appears in the span (dates: the span must show the year, and the month if the
value has one). Responses are cached in `data/cases/<id>/cache/gemini/` and committed; `casefile
metadata` refuses to call Gemini without `--allow-spend`.

First run: 106 documents, 201 fields kept, 0 dropped after allowing dotted dates ("10.13.99"; the first
check dropped 2). 78 of 106 documents have a date. About $0.61 at list price (209k input tokens, 122k
output including thinking).

## What was measured

- All 82 answer-key citations pass the verifier against the ingested case.
- A negative over the real case is refused while one letter is unread and names exactly its pages;
  it verifies once that letter is read.
- Comparing document dates with answer-key event dates mostly shows that an event's date is not its
  document's date (a memo records an earlier meeting; file 19 is a 2006 database printout of 1999
  daily entries). One real error came from OCR in the source (a stamp "12/30/99" read as "12/30/97").
- A sample of 20 documents' metadata read correctly; organisations are recorded as written, including
  the source's own misspellings, so matching names to parties belongs to the party map, not metadata.

## Known limits

- Exact match proves a quote is in the stored text, not that OCR read the page correctly; the UI shows
  the page image beside every quote.
- Logs and registers (daily reports, database printouts) carry a date per entry; document metadata
  holds only the document's own date.
