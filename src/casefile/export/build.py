"""Build the UI bundle for a run from Atlas, and render the cited pages as images.

Everything shown in the UI comes from here: verified claims and refusals with their highlight boxes, the
assembled outputs, the trace, the workers, the harness setup read from the code, and the scores.
"""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from pymongo.database import Database

from casefile.case import CaseConfig
from casefile.evaluation.answer_key import AnswerKey
from casefile.evaluation.score import score_run
from casefile.export.team import build_team
from casefile.export.team_spec import team_spec
from casefile.export.models import (
    Comparison,
    Box,
    Bundle,
    CaseInfo,
    ChronologyRow,
    Claim,
    Coverage,
    DocumentRow,
    ExhibitRow,
    HarnessSpec,
    Highlight,
    KeyEventRow,
    Lane,
    LinkRow,
    PageRef,
    PartyRow,
    RoleSpec,
    RunInfo,
    ScoreRow,
    SplitScore,
    TraceRow,
    WithheldFile,
    WorkerRow,
)
from casefile.harness import examiner as ex
from casefile.harness.assemble import name_key
from casefile.harness.reader import MAX_WORKERS_ACTIVE
from casefile.harness.roles import ROLES
from casefile.ingest.models import page_id as make_page_id

VERIFIER_RULES = [
    "Every quote must be found on the page it cites, after collapsing whitespace and folding curly quotes and dashes. Case, spelling and word order must match.",
    "A quote on a production label (a cover sheet or divider added when the claim file was assembled) is refused.",
    "A quote on a page outside the readable claim file is refused.",
    "An event dated as the document's own date must match the date read from the document, with its source span.",
    "An event dated from the text must have a quote that shows that date.",
    "A party's name must appear in its quotes; a relationship's two parties must both appear in its quotes.",
    "An alias is accepted only when one quote shows both names.",
    "A claim with no citation is shown as interpretation, never as fact.",
    "One failed citation refuses the whole claim. Refused claims are kept with their reasons, not softened.",
]
# Other systems scored by the same verifier and key; shown on the Evaluation screen when their claims exist.
COMPARISONS = {
    "claude-code-1": ("8 Claude agents · no harness",
                      "Claude Sonnet in Claude Code, 8 agents in parallel, one pass of about 10 minutes each over an eighth of "
                      "the pages; a different, stronger model, so this compares model and harness together; nothing records "
                      "which pages were read"),
}
MAX_LANES = 9  # parties with their own lane on the board; the rest share "Other parties"
NEGATIVE_RULE = (
    "Each role proposes what the claim file does not contain at the end of the run, with search terms that would "
    "find a counter-example. A negative is accepted only if every in-scope page was read in the run and a phrase "
    "search for each term finds nothing in scope."
)
MEMORY = {
    "pages / documents / metadata": "the ingested claim file, written only by ingestion",
    "coverage": "every read and search, with the pages it covered",
    "findings": "verified claims",
    "refusals": "refused claims with the verifier's reasons",
    "workers": "every reader started: role, documents, focus, tokens",
    "trace": "one event per step of the run",
    "checkpoints": "LangGraph run state, so a run can stop and resume",
    "outputs": "chronology, party map, exhibits and coverage report",
    "cache": "Reducto and Gemini responses, so nothing is paid for twice",
}


def harness_spec() -> HarnessSpec:
    roles = [
        RoleSpec(role=s.role.value, title=s.title, mirrors=s.mirrors, brief=s.brief, default_focus=s.default_focus,
                 tools=["start readers on documents", "search the case file"],
                 sees="the documents it is assigned, in full")
        for s in ROLES.values()
    ]
    return HarnessSpec(
        examiner_actions=["assign documents to a role, with a focus", "search the case file for an open question",
                          "repair refused claims (once each)", "finish (only when every document has been read)"],
        examiner_sees=["the document list: type, date, author, recipient, page count, who has read it",
                       "progress: pages read, verified and refused claims, readers started",
                       "open questions raised by readers", "refused claims not yet repaired",
                       "never page text or file names"],
        roles=roles,
        guards={"turns": ex.MAX_TURNS, "readers per run": ex.MAX_WORKER_SPAWNS, "readers at once": MAX_WORKERS_ACTIVE,
                "pages per reader": ex.PAGES_PER_READER, "turns without progress": ex.MAX_UNPRODUCTIVE_TURNS,
                "tokens per run": ex.MAX_RUN_TOKENS, "repairs per claim": 1},
        verifier_rules=VERIFIER_RULES, negative_rule=NEGATIVE_RULE, memory_collections=MEMORY,
    )


def _boxes(page: dict, start: int, end: int) -> list[Box]:
    return [Box(left=b["bbox"]["left"], top=b["bbox"]["top"], width=b["bbox"]["width"], height=b["bbox"]["height"])
            for b in page["blocks"] if b["start"] < end and b["end"] > start]


def _checks(c: dict) -> list[str]:
    n = len(c.get("citations", []))
    out = [f"{n} quote{'s' if n != 1 else ''} found on the cited page{'s' if n != 1 else ''}"] if n else []
    p = c["payload"]
    if c["kind"] == "event":
        out.append("date matches the document's date" if p.get("date_source") == "document_date"
                   else "a quote shows the date")
    elif c["kind"] == "party":
        out.append("name appears in the quote")
    elif c["kind"] == "relationship":
        out.append("both parties appear in the quotes")
    elif c["kind"] == "alias":
        out.append("one quote shows both names")
    elif c["kind"] == "negative":
        out.append("every in-scope page was read; no counter-example found by search")
    return out


def _detail(c: dict) -> dict[str, str]:
    p = c["payload"]
    keys = {"party": ["name", "kind", "role"], "relationship": ["source", "type", "target"],
            "alias": ["name", "same_as"], "event": ["date_source"], "negative": ["date_from", "date_to"]}
    return {k: str(p.get(k)) for k in keys.get(c["kind"], []) if p.get(k) is not None}


def _claim(c: dict, pages: dict[str, dict]) -> Claim:
    highlights = []
    matches = {(m["page_id"]): m for m in c.get("matches", [])}
    for q in c.get("citations", []):
        m = matches.get(q["page_id"])
        page = pages.get(q["page_id"])
        boxes = _boxes(page, m["start"], m["end"]) if (m and page) else []
        highlights.append(Highlight(page_id=q["page_id"], quote=q["quote"], boxes=boxes))
    return Claim(id=c["_id"], kind=c["kind"], role=c["role"], worker_id=c["worker_id"], statement=c["statement"],
                 date=c.get("date"), verified=c["verified"], reasons=c.get("reasons", []), checks=_checks(c),
                 highlights=highlights, repair_of=c.get("repair_of"), repair_attempted=bool(c.get("repair_attempted")),
                 detail=_detail(c))


def _score_row(db: Database, key: AnswerKey, run_id: str) -> ScoreRow | None:
    if not db.findings.count_documents({"run_id": run_id}, limit=1):
        return None
    s = score_run(db, key, run_id)
    split = lambda sp: SplitScore(**{k: getattr(sp, k) for k in SplitScore.model_fields})  # noqa: E731
    return ScoreRow(run_id=run_id, dev=split(s.dev), heldout=split(s.heldout), parties_found=s.parties_found,
                    parties_total=s.parties_total, verified_claims=s.verified_claims, refused_claims=s.refused_claims,
                    pages_read=s.pages_read, readers=s.readers, prompt_tokens=s.prompt_tokens,
                    output_tokens=s.output_tokens, cost_usd=s.cost_usd)


def render_pages(case_dir: Path, page_ids: set[str], out_dir: Path, dpi: int = 90) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    def one(pid: str) -> tuple[str, str]:
        _, file_part, page_part = pid.split(":")
        file_no, page = int(file_part), int(page_part[1:])
        name = f"{file_no:03d}-{page:03d}"
        target = out_dir / f"{name}.jpg"
        if not target.exists():
            subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi), "-jpeg", "-jpegopt",
                            "quality=72", "-singlefile", str(case_dir / "raw" / f"{file_no:03d}.pdf"),
                            str(out_dir / name)], check=True, capture_output=True)
        return pid, target.name

    with ThreadPoolExecutor(8) as pool:
        return dict(pool.map(one, sorted(page_ids)))


def build_bundle(db: Database, case_dir: Path, run_id: str, baseline_id: str | None, web_data: Path) -> Bundle:
    case = CaseConfig.model_validate_json((case_dir / "case.json").read_text())
    key = AnswerKey.model_validate(yaml.safe_load((case_dir / "answer_key.yaml").read_text()))
    cid = case.case_id
    pages = {p["_id"]: p for p in db.pages.find({"case_id": cid})}
    metadata = {m["_id"]: m.get("fields", {}) for m in db.metadata.find({"case_id": cid})}
    workers = list(db.workers.find({"run_id": run_id}))
    read_by: dict[str, set[str]] = {}
    for w in workers:
        for d in w["document_ids"]:
            read_by.setdefault(d, set()).add(w["role"])
    documents = []
    for d in db.documents.find({"case_id": cid}).sort("_id", 1):
        m = metadata.get(d["_id"], {})
        documents.append(DocumentRow(
            id=d["_id"], file_no=d["file_no"], doc_type=d["doc_type"],
            date=m.get("date", {}).get("value"), author=m.get("author_org", {}).get("value"),
            recipient=m.get("recipient_org", {}).get("value"),
            page_ids=[make_page_id(cid, d["file_no"], p) for p in d["pages"]], is_label=d["is_label"],
            split_label=d["split_label"], split_confidence=d["confidence"], read_by=sorted(read_by.get(d["_id"], set())),
        ))
    findings = [_claim(c, pages) for c in db.findings.find({"run_id": run_id})]
    refusals = [_claim(c, pages) for c in db.refusals.find({"run_id": run_id})]
    outputs = db.outputs.find_one({"_id": run_id}) or {}

    # key events and which run claims match them (same rule as scoring)
    events = [(c.id, {h.page_id for h in c.highlights}, c.date or "") for c in findings if c.kind == "event"]
    key_rows = []
    for e in key.events:
        pids = [make_page_id(cid, c.file_no, c.page) for c in e.evidence]
        found = [i for i, ps, d in events if set(pids) & ps and d.startswith(e.date)]
        key_rows.append(KeyEventRow(id=e.id, date=e.date, summary=e.summary, core=e.core, split=e.split.value,
                                    ntsb_page=e.ntsb.page, ntsb_quote=e.ntsb.quote, evidence_pages=pids, found_by=found))

    cited = {h.page_id for c in findings + refusals for h in c.highlights} | {p for k in key_rows for p in k.evidence_pages}
    images = render_pages(case_dir, {p for p in cited if p in pages}, web_data / "pages")
    page_refs = {pid: PageRef(page_id=pid, file_no=p["file_no"], page=p["page"],
                              image=f"/data/pages/{images[pid]}" if pid in images else None, is_label=p["is_label"])
                 for pid, p in pages.items()}

    # lanes: the party that wrote each event's document, matched to the party map by name_key
    doc_of_page = {p: d.id for d in documents for p in d.page_ids}
    doc_by_id = {d.id: d for d in documents}
    party_of_key: dict[str, tuple[str, str]] = {}
    for party in outputs.get("parties", []):
        for n in party["names"]:
            party_of_key.setdefault(name_key(n), (party["id"], max(party["names"], key=len)))
    claim_by_id = {c.id: c for c in findings}
    chronology, counts, labels = [], {}, {"other": "Other parties"}
    for r in outputs.get("chronology", []):
        first = claim_by_id.get(r["claim_ids"][0])
        pid = first.highlights[0].page_id if first and first.highlights else None
        doc_id = doc_of_page.get(pid) if pid else None
        author = doc_by_id[doc_id].author if doc_id else None
        lane_id, label = party_of_key.get(name_key(author), ("other", "Other parties")) if author else ("other", "Other parties")
        labels[lane_id] = label
        counts[lane_id] = counts.get(lane_id, 0) + 1
        chronology.append(ChronologyRow(date=r["date"], statement=r["statement"], claim_ids=r["claim_ids"],
                                        roles=r["roles"], document_id=doc_id, lane=lane_id))
    top = [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1]) if k != "other"][:MAX_LANES]
    chronology = [r if r.lane in top else r.model_copy(update={"lane": "other"}) for r in chronology]
    other = sum(v for k, v in counts.items() if k not in top)
    lanes = [Lane(id=k, label=labels[k], events=counts[k]) for k in top]
    if other:
        lanes.append(Lane(id="other", label="Other parties", events=other))

    trace = list(db.trace.find({"run_id": run_id}).sort("seq", 1))
    end = next((t for t in reversed(trace) if t["kind"] == "run_end"), None)
    last_turn = max((t["turn"] for t in trace), default=0)
    status = end["summary"] if end else f"interrupted at turn {last_turn}; resumable from its checkpoint"
    team = build_team(db, run_id)
    if team is not None:
        status = f"team run, stopped because: {team.stop_reason}"
    cov = outputs.get("coverage", {})
    return Bundle(
        case=CaseInfo(case_id=cid, title=case.title, event_date=str(case.event_date), event_summary=case.event_summary,
                      source="https://data.ntsb.gov/Docket/?NTSBNumber=HWY06MH024", inputs=len(case.readable()),
                      withheld=[WithheldFile(file_no=f.file_no, reason=f.reason) for f in case.withheld()]),
        run=RunInfo(run_id=run_id, status=status, turns=last_turn + 1,
                    started_at=str(trace[0]["at"]) if trace else None, ended_at=str(trace[-1]["at"]) if trace else None),
        harness=harness_spec(), documents=documents, pages=page_refs, claims=findings, refusals=refusals,
        chronology=chronology, lanes=lanes,
        parties=[PartyRow(**{k: r[k] for k in PartyRow.model_fields}) for r in outputs.get("parties", [])],
        links=[LinkRow(**{k: r[k] for k in LinkRow.model_fields}) for r in outputs.get("links", [])],
        exhibits=[ExhibitRow(**{k: r[k] for k in ExhibitRow.model_fields}) for r in outputs.get("exhibits", [])],
        negatives=outputs.get("negatives", []),
        coverage=Coverage(**{k: cov.get(k, 0 if k.endswith(("total", "read")) else []) for k in Coverage.model_fields}),
        trace=[TraceRow(seq=t["seq"], turn=t["turn"], kind=t["kind"], summary=t.get("summary") or "", at=str(t["at"]),
                        action=t.get("action"), worker_ids=t.get("worker_ids", []), context_chars=t.get("context_chars"),
                        coverage_pages=t.get("coverage_pages"), verified_total=t.get("verified_total"),
                        refused_total=t.get("refused_total"), tokens=t.get("tokens")) for t in trace],
        workers=[WorkerRow(id=w["_id"], role=w["role"], document_ids=w["document_ids"], pages=len(w.get("page_ids", [])),
                           focus=w.get("focus", ""), verified=w.get("verified", 0), refused=w.get("refused", 0),
                           open_questions=w.get("open_questions", []), prompt_tokens=w.get("prompt_tokens", 0),
                           output_tokens=w.get("output_tokens", 0), thinking_tokens=w.get("thinking_tokens", 0),
                           seconds=w.get("seconds", 0.0)) for w in workers],
        score=_score_row(db, key, run_id), baseline=_score_row(db, key, baseline_id) if baseline_id else None,
        answer_key=key_rows, team=team, team_spec=team_spec(),
        comparisons=[Comparison(label=label, note=note, score=row) for rid, (label, note) in COMPARISONS.items()
                     if (row := _score_row(db, key, rid)) is not None],
    )


def export_run(db: Database, case_dir: Path, run_id: str, baseline_id: str | None, web_root: Path) -> Path:
    data = web_root / "public" / "data"
    bundle = build_bundle(db, case_dir, run_id, baseline_id, data)
    out = data / "runs" / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(bundle.model_dump_json())
    (web_root / "src" / "lib").mkdir(parents=True, exist_ok=True)
    (web_root / "src" / "lib" / "bundle.schema.json").write_text(json.dumps(Bundle.model_json_schema(), indent=1))
    return out
