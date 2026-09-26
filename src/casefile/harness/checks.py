"""Turn a reader's output into stored claims, each verified or refused with reasons.

On top of the Step 4 verifier (every quote on its page; asserted fields match metadata) this adds three
deterministic rules: a party's name must appear in its quote; a relationship's parties must both appear
in its quotes; an event dated from the text needs a quote that shows that date. A name appears if its
words do, ignoring case, punctuation and corporate suffixes; at assembly a name also appears through a
verified alias (B/PB for Bechtel/Parsons Brinckerhoff) quoted in the claim. Negatives are proposed
and checked separately, at the end of the run (`negatives.py`).
"""

import hashlib
import json
import re
from datetime import UTC, datetime

from casefile.harness.models import (
    AliasClaim,
    ClaimKind,
    DateSource,
    EventClaim,
    PartyMention,
    QuoteRef,
    ReaderOutput,
    RelationshipClaim,
    Role,
    StoredClaim,
)
from casefile.ingest.metadata import date_matches_span
from casefile.verify.index import CaseIndex
from casefile.verify.models import AssertedFields, Citation, Claim, Status
from casefile.verify.text import FOLD
from casefile.verify.verifier import verify_claim


def _fold(s: str) -> str:
    return " ".join(s.translate(FOLD).lower().split())


SUFFIXES = {"inc", "incorporated", "co", "company", "companies", "corp", "corporation", "llc", "ltd", "the"}
NOT_IN_QUOTES = "does not appear in the quotes"


def name_key(name: str) -> str:
    """A party name with formatting removed: case, punctuation and corporate suffixes. Two names with the
    same key are the same party written differently; nothing else is merged without a quoted alias."""
    words = re.sub(r"[^\w\s]", " ", name.translate(FOLD).lower()).split()
    return " ".join(w for w in words if w not in SUFFIXES)


def _name_in(name: str, quotes: list[QuoteRef]) -> bool:
    key = name_key(name)
    return _fold(name) in " ".join(_fold(q.quote) for q in quotes) or bool(key) and any(
        f" {key} " in f" {name_key(q.quote)} " for q in quotes)


def _names_of(claim: StoredClaim) -> list[str]:
    p = claim.payload
    if isinstance(p, PartyMention):
        return [p.name]
    if isinstance(p, RelationshipClaim):
        return [p.source, p.target]
    if isinstance(p, AliasClaim):
        return [p.name, p.same_as]
    return []


def _names_present(names: list[str], quotes: list[QuoteRef]) -> list[str]:
    return [f"{name!r} {NOT_IN_QUOTES}" for name in names if not _name_in(name, quotes)]


def reinstate_by_alias(refused: list[StoredClaim], aliases: list[StoredClaim]) -> list[StoredClaim]:
    """Refused claims whose only fault is a party name absent from the quotes, where a verified alias of that
    name is in the quotes instead. Returned verified, with the alias claim recorded for each name."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    verified = [a for a in aliases if a.verified and isinstance(a.payload, AliasClaim)]
    for a in verified:
        parent[find(name_key(a.payload.name))] = find(name_key(a.payload.same_as))
    out = []
    for claim in refused:
        missing = [n for n in _names_of(claim) if not _name_in(n, claim.citations)]
        if not missing or len(claim.reasons) != len(missing) or not all(r.endswith(NOT_IN_QUOTES) for r in claim.reasons):
            continue
        resolved: dict[str, str] = {}
        for name in missing:
            root = find(name_key(name))
            for a in verified:
                if find(name_key(a.payload.name)) == root and any(
                        _name_in(n, claim.citations) for n in (a.payload.name, a.payload.same_as)):
                    resolved[name] = a.id
                    break
        if len(resolved) == len(missing):
            out.append(claim.model_copy(update={"verified": True, "reasons": [], "name_aliases": resolved}))
    return out


def _claim_id(run_id: str, kind: ClaimKind, payload) -> str:
    digest = hashlib.sha256(json.dumps([run_id, kind, payload.model_dump(mode="json")], sort_keys=True).encode())
    return f"{kind.value[:3]}-{digest.hexdigest()[:12]}"


def _verify(quotes: list[QuoteRef], index: CaseIndex, asserted: AssertedFields = AssertedFields()):
    claim = Claim(id="x", statement="", citations=[Citation(page_id=q.page_id, quote=q.quote) for q in quotes], asserted=asserted)
    verdict = verify_claim(claim, index)
    return verdict.status is Status.VERIFIED, list(verdict.reasons), [m.model_dump() for m in verdict.matches]


def _event(e: EventClaim, index: CaseIndex) -> tuple[bool, list[str], list]:
    if e.date_source is DateSource.DOCUMENT_DATE:
        return _verify(e.quotes, index, AssertedFields(date=e.date))
    ok, reasons, matches = _verify(e.quotes, index)
    if not any(date_matches_span(e.date, q.quote) for q in e.quotes):
        reasons.append(f"no quote shows the date {e.date}")
    return not reasons, reasons, matches


def check_output(
    output: ReaderOutput, index: CaseIndex, *, run_id: str, case_id: str, role: Role, worker_id: str,
    repair_of: str | None = None,
) -> list[StoredClaim]:
    now = datetime.now(UTC)
    stored: list[StoredClaim] = []

    def add(kind, payload, statement, quotes, result, date=None):
        verified, reasons, matches = result
        stored.append(StoredClaim(
            id=_claim_id(run_id, kind, payload), run_id=run_id, case_id=case_id, kind=kind, role=role,
            worker_id=worker_id, statement=statement, date=date, citations=quotes, payload=payload,
            verified=verified, reasons=reasons, matches=matches, repair_of=repair_of, created_at=now,
        ))

    for e in output.events:
        try:
            result = _event(e, index)
        except ValueError as exc:  # malformed date
            result = (False, [str(exc)], [])
        date = e.date if result[0] else None
        add(ClaimKind.EVENT, e, e.statement, e.quotes, result, date=date)
    for p in output.parties:
        ok, reasons, matches = _verify(p.quotes, index)
        reasons += _names_present([p.name], p.quotes)
        add(ClaimKind.PARTY, p, f"{p.name} ({p.role})", p.quotes, (not reasons, reasons, matches))
    for r in output.relationships:
        ok, reasons, matches = _verify(r.quotes, index)
        reasons += _names_present([r.source, r.target], r.quotes)
        add(ClaimKind.RELATIONSHIP, r, f"{r.source} {r.type.value} {r.target}", r.quotes, (not reasons, reasons, matches))
    for a in output.aliases:
        ok, reasons, matches = _verify([a.quote], index)
        reasons += _names_present([a.name, a.same_as], [a.quote])
        add(ClaimKind.ALIAS, a, f"{a.name} = {a.same_as}", [a.quote], (not reasons, reasons, matches))
    return stored


