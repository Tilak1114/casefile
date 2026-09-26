"""The trajectory of a v2 team run, read back from MongoDB for the UI: events, tasks, readers, progress.

Times are seconds since `claim_file.opened`. A task starts when its trigger event was published and ends at
its last update; a reader starts when the harness logged its pages (before the model ran) and lasts as long
as its model call. Nothing here is estimated beyond that.
"""

from datetime import datetime

from pymongo.database import Database

from casefile.export.models import TeamCall, TeamEvent, TeamExclusion, TeamPoint, TeamReader, TeamRun, TeamTask


def _ts(v) -> datetime:
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)


def _summary(e: dict) -> str:
    p = e.get("payload") or {}
    for k in ("focus", "summary", "statement", "reason", "ruling", "question", "scope", "guard"):
        if p.get(k):
            text = str(p[k])
            if k == "guard":
                text = f"guard: {text}" + (f" ({p['unfinished_documents']} documents unfinished)" if "unfinished_documents" in p else "")
            return text
    if "verified" in p:
        return "verified" if p["verified"] else "refused: " + "; ".join(p.get("reasons", []))
    if "documents" in p:
        return f"{p['documents']} documents in the claim file"
    return ""


def _decision(actor: str, output: dict | None) -> dict | None:
    if output is None:
        return None
    if actor.endswith("-reader"):
        return {k: len(v) for k, v in output.items() if isinstance(v, list)}
    return output


def build_team(db: Database, run_id: str) -> TeamRun | None:
    raw = list(db.events.find({"run_id": run_id}).sort("seq", 1))
    if not raw:
        return None
    t0 = _ts(raw[0]["at"])
    rel = lambda v: round((_ts(v) - t0).total_seconds(), 2)  # noqa: E731
    seq_of = {e["_id"]: e["seq"] for e in raw}
    events = [TeamEvent(seq=e["seq"], t=rel(e["at"]), type=e["type"], sender=e["sender"], to=e.get("to"),
                        subjects=len(e.get("subject_ids", [])), correlation_id=e["correlation_id"],
                        causation_seq=seq_of.get(e.get("causation_id")), summary=_summary(e),
                        document_ids=list((e.get("payload") or {}).get("document_ids", []) or []))
              for e in raw]
    at_of_event = {e["_id"]: rel(e["at"]) for e in raw}
    calls = list(db.model_calls.find({"run_id": run_id}).sort("at", 1))
    by_task: dict[str, list[dict]] = {}
    for c in calls:
        by_task.setdefault(c.get("task_id") or "", []).append(c)
    tasks = []
    for t in db.tasks.find({"run_id": run_id}):
        mine = by_task.get(t["_id"], [])
        tasks.append(TeamTask(
            id=t["_id"], role=t["role"], kind=t["kind"], state=t["state"], trigger_seq=seq_of.get(t["trigger_event_id"]),
            start=at_of_event.get(t["trigger_event_id"], 0.0), end=rel(t["updated_at"]) if t.get("updated_at") else None,
            note=t.get("note") or "", calls=len(mine), cost_usd=round(sum(c.get("cost_usd", 0) for c in mine), 4)))
    tasks.sort(key=lambda x: x.start)
    task_of_doc = {(r["role"], r["document_id"]): r["task_id"] for r in db.reservations.find({"run_id": run_id})}
    coverage = {c["_id"]: c for c in db.coverage.find({"run_id": run_id})}
    readers = []
    for w in db.workers.find({"run_id": run_id}):
        cov = coverage.get(w.get("coverage_id"))
        if cov is None:
            continue
        start = rel(cov["created_at"])
        readers.append(TeamReader(
            id=w["_id"], role=w["role"], task_id=next((task_of_doc.get((w["role"], d)) for d in w["document_ids"]
                                                      if (w["role"], d) in task_of_doc), None),
            start=start, end=round(start + w.get("seconds", 0.0), 2), document_ids=w["document_ids"],
            pages=len(w.get("page_ids", [])), verified=w.get("verified", 0), refused=w.get("refused", 0), focus=w.get("focus", "")))
    readers.sort(key=lambda r: r.start)

    # cumulative progress: distinct pages given to readers, claims verified and refused, cost
    marks: list[tuple[float, str, object]] = []
    for c in coverage.values():
        if c.get("mode") == "read":
            marks.append((rel(c["created_at"]), "pages", c["page_ids"]))
    for coll, kind in (("findings", "verified"), ("refusals", "refused")):
        for f in db[coll].find({"run_id": run_id}, {"created_at": 1}):
            if f.get("created_at"):
                marks.append((rel(f["created_at"]), kind, 1))
    for c in calls:
        marks.append((rel(c["at"]), "cost", c.get("cost_usd", 0.0)))
    marks.sort(key=lambda m: m[0])
    seen: set[str] = set()
    verified = refused = 0
    cost = 0.0
    series: list[TeamPoint] = []
    for t, kind, v in marks:
        if kind == "pages":
            seen |= set(v)
        elif kind == "verified":
            verified += 1
        elif kind == "refused":
            refused += 1
        else:
            cost += v
        point = TeamPoint(t=t, pages=len(seen), verified=verified, refused=refused, cost_usd=round(cost, 4))
        if series and series[-1].t == t:
            series[-1] = point
        else:
            series.append(point)
    summary = db.team_runs.find_one({"_id": run_id}) or {}
    end = max([events[-1].t] + [c for c in (rel(x["at"]) for x in calls)] + [r.end for r in readers])
    return TeamRun(
        started_at=str(raw[0]["at"]), duration_s=round(end, 1), stop_reason=summary.get("stop_reason", "unknown"),
        cost_usd=round(sum(c.get("cost_usd", 0) for c in calls), 4), call_count=len(calls), events=events, tasks=tasks,
        readers=readers, series=series,
        exclusions=[TeamExclusion(document_id=x["document_id"], reason=x["reason"]) for x in db.exclusions.find({"run_id": run_id})],
        calls=[TeamCall(id=str(c["_id"]), actor=c["actor"], purpose=c["purpose"], task_id=c.get("task_id"), ref=c.get("ref"),
                        t=rel(c["at"]), cost_usd=round(c.get("cost_usd", 0.0), 5), prompt_tokens=c.get("prompt_tokens", 0),
                        output_tokens=c.get("output_tokens", 0), reasoning_tokens=c.get("reasoning_tokens", 0),
                        reasoning=c.get("reasoning") or "", decision=_decision(c["actor"], c.get("output")))
               for c in calls],
        reasoning_recorded=any(c.get("reasoning") for c in calls),
    )
