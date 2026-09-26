"""What each agent is shown, rebuilt from MongoDB for every task. The lead never sees page text."""

from pymongo.database import Database

from casefile.verify.index import CaseIndex


def exclusions(db: Database, run_id: str) -> dict[str, str]:
    return {e["document_id"]: e["reason"] for e in db.exclusions.find({"run_id": run_id})}


def read_by(db: Database, run_id: str, index: CaseIndex) -> dict[str, set[str]]:
    """Document id -> actors who were given its pages in full."""
    page_to_doc = {p: d.id for d in index.documents.values() for p in d.page_ids}
    out: dict[str, set[str]] = {}
    for r in db.coverage.find({"run_id": run_id, "mode": "read"}, {"page_ids": 1, "actor": 1}):
        who = (r.get("actor") or "?").split(" ")[0]
        for p in r["page_ids"]:
            if p in page_to_doc:
                out.setdefault(page_to_doc[p], set()).add(who)
    return out


def document_index(db: Database, run_id: str, index: CaseIndex, *, only: set[str] | None = None) -> str:
    """One line per readable document: id | type | date | from -> to | pages | read by | excluded."""
    who = read_by(db, run_id, index)
    excl = exclusions(db, run_id)
    lines = []
    for d in sorted((d for d in index.documents.values() if not d.is_label), key=lambda d: (d.date or "9999", d.id)):
        if only is not None and d.id not in only:
            continue
        m = d.metadata
        status = "excluded" if d.id in excl else (",".join(sorted(who.get(d.id, set()))) or "unread")
        lines.append(f"{d.id} | {d.doc_type} | {m.date.value if m.date else '?'} | "
                     f"{m.author_org.value if m.author_org else '?'} -> {m.recipient_org.value if m.recipient_org else '?'} | "
                     f"{len(d.page_ids)}p | {status}")
    return "\n".join(lines)


def unfinished_documents(db: Database, run_id: str, index: CaseIndex) -> list[str]:
    """Readable documents neither read in full by anyone nor excluded with a reason."""
    who = read_by(db, run_id, index)
    excl = exclusions(db, run_id)
    return [d.id for d in index.documents.values() if not d.is_label and d.id not in who and d.id not in excl]


def own_claims(db: Database, run_id: str, role: str, limit: int = 200) -> str:
    rows = db.findings.find({"run_id": run_id, "role": role}, {"_id": 1, "kind": 1, "date": 1, "statement": 1}).sort("date", 1)
    return "\n".join(f"{c['_id']} | {c['kind']} | {c.get('date') or ''} | {c['statement'][:160]}" for c in list(rows)[:limit])


def open_questions(db: Database, run_id: str, role: str, limit: int = 15) -> list[str]:
    seen: list[str] = []
    for w in db.workers.find({"run_id": run_id, "role": role}).sort("_id", -1):
        for q in w.get("open_questions", []):
            if q not in seen:
                seen.append(q)
    return seen[:limit]
