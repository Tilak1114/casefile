"""Score a run's verified findings against the answer key, dev and held-out separately.

- Event: found if a verified event cites one of the key event's evidence pages and its date agrees at the
  key's precision (the key's date is a prefix of the run's date).
- Party: found if one of the run's party names and the key's name contain each other (case-folded).
- Relationship: found if the run has a verified link of the same type between parties matching the key's.
- Negatives are listed side by side, not auto-matched: matching free-text absences would need judgement.
"""

from pydantic import BaseModel
from pymongo.database import Database

import re

from casefile.evaluation.answer_key import AnswerKey, Split
from casefile.harness.assemble import name_key
from casefile.ingest.models import page_id
from casefile.verify.text import FOLD

# Gemini list prices per 1M tokens (ai.google.dev/pricing, read 2026-09-26), gemini-3.8-flash standard tier.
PRICE_INPUT = 0.75
PRICE_OUTPUT = 3.75


def _fold(s: str) -> str:
    return " ".join(s.translate(FOLD).lower().replace("/", " ").split())


class SplitScore(BaseModel):
    events_found: int
    events_total: int
    core_found: int
    core_total: int
    relationships_found: int
    relationships_total: int
    missed_events: list[str]


class RunScore(BaseModel):
    run_id: str
    dev: SplitScore
    heldout: SplitScore
    parties_found: int
    parties_total: int
    verified_claims: int
    refused_claims: int
    pages_read: int
    readers: int
    prompt_tokens: int
    output_tokens: int
    cost_usd: float
    run_negatives: list[str]
    key_negatives: list[str]


def _variants(name: str) -> list[str]:
    """A key name like "Bechtel/Parsons Brinckerhoff (B/PB)" also stands for its parenthesised short form."""
    inner = re.findall(r"\(([^)]+)\)", name)
    return [n for n in [name_key(re.sub(r"\([^)]*\)", "", name)), *map(name_key, inner)] if n]


def _names_match(key_name: str, run_name: str) -> bool:
    r = name_key(run_name)
    return bool(r) and any(v == r or (len(v) > 3 and (v in r or r in v)) for v in _variants(key_name))


def score_run(db: Database, key: AnswerKey, run_id: str) -> RunScore:
    findings = list(db.findings.find({"run_id": run_id}))
    events = [f for f in findings if f["kind"] == "event"]
    event_pages = [({c["page_id"] for c in e["citations"]}, e.get("date") or "") for e in events]
    run_parties = [f["payload"]["name"] for f in findings if f["kind"] == "party"]
    outputs = db.outputs.find_one({"_id": run_id}) or {}
    clusters = {p["id"]: p["names"] for p in outputs.get("parties", [])}

    def party_ids(name: str) -> set[str]:
        return {pid for pid, names in clusters.items() if any(_names_match(name, n) for n in names)}

    def split_score(split: Split) -> SplitScore:
        evs = [e for e in key.events if e.split is split]
        found, missed = [], []
        for e in evs:
            pages = {page_id(key.case_id, c.file_no, c.page) for c in e.evidence}
            if any(pages & ps and d.startswith(e.date) for ps, d in event_pages):
                found.append(e)
            else:
                missed.append(f"{e.id} {e.date} {e.summary[:80]}")
        rels = [r for r in key.relationships if r.split is split]
        by_id = {p.id: p for p in key.parties}
        rel_found = 0
        for r in rels:
            src, tgt = party_ids(by_id[r.source].name), party_ids(by_id[r.target].name)
            if any(link["type"] == r.type.value and link["source"] in src and link["target"] in tgt
                   for link in outputs.get("links", [])):
                rel_found += 1
        return SplitScore(
            events_found=len(found), events_total=len(evs), core_found=sum(e.core for e in found),
            core_total=sum(e.core for e in evs), relationships_found=rel_found, relationships_total=len(rels),
            missed_events=missed,
        )

    workers = list(db.workers.find({"run_id": run_id}))
    decisions = list(db.trace.find({"run_id": run_id, "kind": {"$in": ["decision", "rejected"]}}))
    prompt = sum(w["prompt_tokens"] for w in workers)
    output = sum(w["output_tokens"] + w["thinking_tokens"] for w in workers)
    examiner = sum(d.get("tokens") or 0 for d in decisions)  # examiner prompt+output, not split; priced as input
    cost = (prompt + examiner) / 1e6 * PRICE_INPUT + output / 1e6 * PRICE_OUTPUT
    return RunScore(
        run_id=run_id, dev=split_score(Split.DEV), heldout=split_score(Split.HELDOUT),
        parties_found=sum(any(_names_match(p.name, n) for n in run_parties) for p in key.parties),
        parties_total=len(key.parties), verified_claims=len(findings), refused_claims=db.refusals.count_documents({"run_id": run_id}),
        pages_read=len({p for r in db.coverage.find({"run_id": run_id, "mode": "read"}) for p in r["page_ids"]}),
        readers=len(workers), prompt_tokens=prompt + examiner, output_tokens=output, cost_usd=round(cost, 2),
        run_negatives=outputs.get("negatives", []), key_negatives=[n.statement for n in key.negatives],
    )
