"""Turn a reader's output into stored claims, each verified or refused with reasons.

On top of the Step 4 verifier (every quote on its page; asserted fields match metadata) this adds three
deterministic rules: a party's name must appear in its quote; a relationship's parties must both appear
in its quotes; an event dated from the text needs a quote that shows that date. Negatives are proposed
and checked separately, at the end of the run (`negatives.py`).
"""

import hashlib
import json
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


def _names_present(names: list[str], quotes: list[QuoteRef]) -> list[str]:
    joined = " ".join(_fold(q.quote) for q in quotes)
    return [f"{name!r} does not appear in the quotes" for name in names if _fold(name) not in joined]


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


