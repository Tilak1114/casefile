"""End of run: propose and check negatives, then assemble the outputs with code.

Negatives are proposed by each role with the whole document list in view, and accepted only if every
page in scope was read in this run and a search for the role's own counter-example terms finds nothing
in scope. The party map, chronology, exhibit list and coverage report are assembled deterministically
from verified claims.
"""

import hashlib
import re
from datetime import UTC, datetime

from pydantic import BaseModel

from casefile.case import CaseConfig
from casefile.harness.examiner import Deps, readable_documents
from casefile.harness.models import (
    AbsenceClaim,
    AliasClaim,
    ClaimKind,
    EventClaim,
    NegativesOutput,
    PartyMention,
    RelationshipClaim,
    Role,
    StoredClaim,
)
from casefile.harness.roles import ROLES
from casefile.search import search_pages
from casefile.verify.models import NegativeClaim, NegativeScope, Status
from casefile.verify.text import FOLD
from casefile.verify.verifier import _in_window, verify_negative

NEGATIVES_PROMPT = """{role_brief}

Your team has read the case file. Below are the documents it contains and the facts your readers
verified. State what the case file does NOT contain that matters to the claim: records one would expect
and cannot find (a test, an approval, a response, a notice). For each, give the document types and date
window it covers, and short search phrases that would appear on a page contradicting it. Only propose
absences you are confident about; each will be checked by searching every page in scope.

Documents (id | type | date | from -> to):
{documents}

Verified facts:
{facts}"""


def _fold(s: str) -> str:
    return " ".join(s.translate(FOLD).lower().split())


SUFFIXES = {"inc", "incorporated", "co", "company", "companies", "corp", "corporation", "llc", "ltd", "the"}


def name_key(name: str) -> str:
    """A party name with formatting removed: case, punctuation and corporate suffixes. Two names with the
    same key are the same party written differently; nothing else is merged without a quoted alias."""
    words = re.sub(r"[^\w\s]", " ", name.translate(FOLD).lower()).split()
    return " ".join(w for w in words if w not in SUFFIXES)


def propose_and_check_negatives(deps: Deps, turn: int) -> tuple[int, int]:
    docs = readable_documents(deps.index)
    listing = "\n".join(
        f"{d.id} | {d.doc_type} | {d.metadata.date.value if d.metadata.date else '?'} | "
        f"{d.metadata.author_org.value if d.metadata.author_org else '?'} -> "
        f"{d.metadata.recipient_org.value if d.metadata.recipient_org else '?'}" for d in docs)
    records = deps.coverage.records()
    accepted = refused = 0
    for role in (Role.PARTIES, Role.TECHNICAL):
        facts = [f"- {c.date or ''} {c.statement}" for c in deps.store.claims("findings") if c.role is role]
        prompt = NEGATIVES_PROMPT.format(role_brief=ROLES[role].brief, documents=listing, facts="\n".join(facts[:300]))
        output, _, _ = deps.gemini.structured(f"negatives-{role.value}", prompt, NegativesOutput)
        for absence in output.absences:
            claim = check_negative(absence, deps, records)
            deps.store.save_claims([claim.model_copy(update={"role": role})])
            accepted += claim.verified
            refused += not claim.verified
    return accepted, refused


def check_negative(absence: AbsenceClaim, deps: Deps, records) -> StoredClaim:
    scope = NegativeScope(doc_types=absence.doc_types, date_from=absence.date_from, date_to=absence.date_to)
    negative = NegativeClaim(id="n", statement=absence.statement, scope=scope, coverage_ids=list(records) or ["none"])
    verdict = verify_negative(negative, deps.index, records)
    reasons = list(verdict.reasons)
    in_scope = {p for d in deps.index.documents.values()
                if not d.is_label and d.doc_type in scope.doc_types and _in_window(d, scope.date_from, scope.date_to)
                for p in d.page_ids}
    if not in_scope:
        reasons.append("no documents of these types in the window; nothing to be absent from")
    for term in absence.search_terms:
        hits = [h["_id"] for h in search_pages(deps.store.db, deps.index.case_id, term, limit=20, phrase=True) if h["_id"] in in_scope]
        if hits:
            reasons.append(f"search for {term!r} found it on {', '.join(hits[:3])}")
    digest = hashlib.sha256(absence.model_dump_json().encode()).hexdigest()[:12]
    return StoredClaim(
        id=f"neg-{digest}", run_id=deps.store.run_id, case_id=deps.index.case_id, kind=ClaimKind.NEGATIVE,
        role=Role.TECHNICAL, worker_id="negatives", statement=absence.statement, payload=absence,
        verified=verdict.status is Status.VERIFIED and not reasons, reasons=reasons, created_at=datetime.now(UTC),
    )


# ---- outputs --------------------------------------------------------------------------------------


class ChronologyEntry(BaseModel):
    date: str
    statement: str
    claim_ids: list[str]
    roles: list[str]
    citations: list[dict]


class Party(BaseModel):
    id: str
    names: list[str]
    kind: str
    roles: list[str]
    claim_ids: list[str]


class PartyLink(BaseModel):
    source: str
    type: str
    target: str
    claim_ids: list[str]


class Exhibit(BaseModel):
    document_id: str
    doc_type: str
    date: str | None
    file_no: int
    sha256: str
    cited_by: int


class CoverageReport(BaseModel):
    documents_total: int
    documents_read: int
    pages_total: int
    pages_read: int
    unread_documents: list[str]
    searched_only_pages: list[str]
    withheld_files: list[int]


class RunOutputs(BaseModel):
    run_id: str
    case_id: str
    chronology: list[ChronologyEntry]
    parties: list[Party]
    links: list[PartyLink]
    exhibits: list[Exhibit]
    negatives: list[str]
    coverage: CoverageReport
    assembled_at: datetime


def _party_clusters(parties: list[StoredClaim], aliases: list[StoredClaim]) -> tuple[list[Party], dict[str, str]]:
    """Union names that a verified alias claim quotes together; otherwise names stay separate."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in parties:
        find(name_key(p.payload.name))
    for a in aliases:
        assert isinstance(a.payload, AliasClaim)
        parent[find(name_key(a.payload.name))] = find(name_key(a.payload.same_as))
    groups: dict[str, list[StoredClaim]] = {}
    for p in parties:
        groups.setdefault(find(name_key(p.payload.name)), []).append(p)
    names_of: dict[str, set[str]] = {}
    for a in aliases:
        root = find(name_key(a.payload.name))
        names_of.setdefault(root, set()).update({a.payload.name, a.payload.same_as})
    clusters, by_name = [], {}
    for i, (root, members) in enumerate(sorted(groups.items())):
        assert all(isinstance(m.payload, PartyMention) for m in members)
        names = sorted({m.payload.name for m in members} | names_of.get(root, set()))
        pid = f"party-{i + 1:02d}"
        clusters.append(Party(id=pid, names=names, kind=members[0].payload.kind,
                              roles=sorted({m.payload.role for m in members}), claim_ids=[m.id for m in members]))
        for n in names:
            by_name[name_key(n)] = pid
    return clusters, by_name


def assemble(deps: Deps, case: CaseConfig, manifest_sha: dict[int, str]) -> RunOutputs:
    findings = deps.store.claims("findings")
    events = [c for c in findings if c.kind is ClaimKind.EVENT]
    merged: dict[tuple[str, str], ChronologyEntry] = {}
    for e in sorted(events, key=lambda c: (c.date or "", c.id)):
        assert isinstance(e.payload, EventClaim)
        key = (e.date or "", e.citations[0].page_id)  # same date, same first page: one entry
        if key in merged:
            merged[key].claim_ids.append(e.id)
            merged[key].roles = sorted(set(merged[key].roles) | {e.role.value})
        else:
            merged[key] = ChronologyEntry(date=e.date or "", statement=e.statement, claim_ids=[e.id], roles=[e.role.value],
                                          citations=[m for m in e.matches])
    parties, by_name = _party_clusters([c for c in findings if c.kind is ClaimKind.PARTY],
                                       [c for c in findings if c.kind is ClaimKind.ALIAS])
    links: dict[tuple[str, str, str], PartyLink] = {}
    for r in (c for c in findings if c.kind is ClaimKind.RELATIONSHIP):
        assert isinstance(r.payload, RelationshipClaim)
        s, t = by_name.get(name_key(r.payload.source)), by_name.get(name_key(r.payload.target))
        s, t = s or r.payload.source, t or r.payload.target
        key = (s, r.payload.type.value, t)
        links.setdefault(key, PartyLink(source=s, type=key[1], target=t, claim_ids=[])).claim_ids.append(r.id)
    cited: dict[str, int] = {}
    for c in findings:
        for q in c.citations:
            doc = deps.index.document_of(q.page_id)
            if doc:
                cited[doc.id] = cited.get(doc.id, 0) + 1
    exhibits = []
    for doc_id, n in sorted(cited.items()):
        doc = deps.index.documents[doc_id]
        file_no = deps.index.pages[doc.page_ids[0]].file_no
        exhibits.append(Exhibit(document_id=doc_id, doc_type=doc.doc_type, date=doc.date, file_no=file_no,
                                sha256=manifest_sha[file_no], cited_by=n))
    docs = readable_documents(deps.index)
    pages = {p for d in docs for p in d.page_ids if not deps.index.pages[p].is_label}
    read = deps.store.pages_read() & pages
    searched = {p for r in deps.store.db.coverage.find({"run_id": deps.store.run_id, "mode": "search"}) for p in r["page_ids"]}
    unread_docs = [d.id for d in docs if not set(d.page_ids) & read]
    outputs = RunOutputs(
        run_id=deps.store.run_id, case_id=deps.index.case_id,
        chronology=list(merged.values()), parties=parties, links=list(links.values()), exhibits=exhibits,
        negatives=[c.statement for c in findings if c.kind is ClaimKind.NEGATIVE],
        coverage=CoverageReport(
            documents_total=len(docs), documents_read=len(docs) - len(unread_docs), pages_total=len(pages),
            pages_read=len(read), unread_documents=unread_docs, searched_only_pages=sorted((searched & pages) - read),
            withheld_files=[f.file_no for f in case.withheld()],
        ),
        assembled_at=datetime.now(UTC),
    )
    deps.store.db.outputs.replace_one({"_id": deps.store.run_id}, {"_id": deps.store.run_id, **outputs.model_dump(mode="json")}, upsert=True)
    return outputs
