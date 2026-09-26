"""The single-prompt baseline: every readable page in one Gemini call, the same claim schema, the same
checks and the same scoring as the harness. If the harness does not beat this, it has not earned its keep.
"""

from casefile.case import CaseConfig
from casefile.harness.assemble import assemble
from casefile.harness.checks import check_output
from casefile.harness.examiner import Deps, readable_documents
from casefile.harness.models import ReaderOutput, Role, TraceKind
from casefile.harness.reader import render_documents

BASELINE_PROMPT = """You are reviewing a construction claim file. From the documents below, report dated events
(design requirements, submittals and approvals, tests and results, problems reported, repairs), the parties
and how they are related, names written differently for the same party, and open questions.

Rules:
- Report only what the documents say. No opinions about cause, fault or liability.
- Every claim needs quotes copied character for character from the page text, with the id of the page
  each quote is on. Quote 5 to 40 words.
- Events: date_source "document_date" when the event is the document itself; "stated_in_text" when the
  text says when something happened, and then one quote must show that date.
- Write party names exactly as they appear in your quotes.

{documents}"""


def run_baseline(deps: Deps, case: CaseConfig, manifest_sha: dict[int, str]) -> dict:
    docs = readable_documents(deps.index)
    text, page_ids = render_documents(docs, deps.index)
    deps.coverage.read(page_ids)
    deps.store.trace(0, TraceKind.RUN_START, f"baseline: one prompt with {len(docs)} documents, {len(page_ids)} pages")
    output, usage, cached = deps.gemini.structured("baseline", BASELINE_PROMPT.format(documents=text), ReaderOutput)
    claims = check_output(output, deps.index, run_id=deps.store.run_id, case_id=deps.index.case_id,
                          role=Role.TECHNICAL, worker_id="baseline")
    verified, refused = deps.store.save_claims(claims)
    deps.store.db.workers.replace_one(
        {"_id": f"{deps.store.run_id}-w"},
        {"_id": f"{deps.store.run_id}-w", "run_id": deps.store.run_id, "role": "baseline", "document_ids": [d.id for d in docs],
         "page_ids": page_ids, "prompt_tokens": usage.prompt_tokens, "output_tokens": usage.output_tokens,
         "thinking_tokens": usage.thinking_tokens, "open_questions": output.open_questions, "cached": cached},
        upsert=True,
    )
    outputs = assemble(deps, case, manifest_sha)
    deps.store.trace(0, TraceKind.RUN_END, f"baseline: {verified} verified, {refused} refused",
                     verified_total=verified, refused_total=refused)
    return {"verified": verified, "refused": refused, "chronology": len(outputs.chronology),
            "prompt_tokens": usage.prompt_tokens, "output_tokens": usage.output_tokens + usage.thinking_tokens}
