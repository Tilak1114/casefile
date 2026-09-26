"""The claim professional (lead). Never sees page text; decides from the index, reports and open items.

Each lead task is one decision about the event that woke it. The lead retains the forensic engineer when counsel
asks or on its own initiative, as a claim professional does. The harness validates every decision: document
ids must exist, the engineer can only be assigned work after approval, rulings must cite claims in the
dispute, and the claim file closes only when every document is read or excluded and nothing is open.
"""

from pydantic import BaseModel, Field

from casefile.team import context
from casefile.team.dispatcher import Dispatcher
from casefile.team.events import Actor, Event, EventType as E
from casefile.team.reviewer import TeamDeps
from casefile.verify.index import CaseIndex
from casefile.team.store import TaskState

BRIEF = ("You are the claim professional who owns this construction-defect liability claim file. You assign work to "
         "defense counsel and, once you approve its retention, the forensic engineer. You never read documents yourself "
         "and you never state fault, liability or coverage. Your job is to get every document read by the right role or "
         "excluded with a reason, follow up open questions, rule disputes on the evidence, and close the claim file.")


class Exclusion(BaseModel):
    document_ids: list[str]
    reason: str = Field(description="Why these documents need not be read in full, e.g. bulk test data tables.")


class Assignment(BaseModel):
    role: str = Field(description="counsel or engineer")
    document_ids: list[str]
    focus: str


class Retention(BaseModel):
    reason: str = Field(description="Why technical documents need a forensic engineer's reading.")
    focus: str = Field(description="The engineer's scope.")
    document_ids: list[str] = Field([], description="Documents the engineer should read first.")


RETAIN = ("If the claim file holds technical material (testing, laboratory, inspection or design documents) that "
          "needs an engineer's reading, retain the forensic engineer with a scope; otherwise leave retain_engineer empty.")


class Opening(BaseModel):
    thinking: str
    counsel_focus: str = Field(description="What defense counsel should establish first.")
    exclusions: list[Exclusion] = []
    retain_engineer: Retention | None = None


class ExpertDecision(BaseModel):
    approve: bool
    reason: str
    focus: str = Field(description="The engineer's scope, if approved.")
    document_ids: list[str] = Field([], description="Documents the engineer should read first.")


class NextStep(BaseModel):
    thinking: str
    assignments: list[Assignment] = []
    exclusions: list[Exclusion] = []
    retain_engineer: Retention | None = Field(None, description="Only if the engineer is not yet approved.")
    close: bool = Field(description="True only if every document is read or excluded and nothing is open.")


class Ruling(BaseModel):
    favoured_claim_id: str = Field(description="The claim the record supports better.")
    ruling: str = Field(description="Why, citing the documents' own words.")


class Brief(BaseModel):
    summary: str = Field(description="What the claim file shows, as documented facts; no fault or cause.")
    key_claim_ids: list[str]


def _state(deps: TeamDeps) -> str:
    db, run = deps.store.db, deps.store.run_id
    unfinished = context.unfinished_documents(db, run, deps.index)
    reports = [e for e in deps.dispatcher.store.events() if e.type is E.REPORT_SUBMITTED]
    open_tasks = [t for t in deps.dispatcher.store.tasks() if t.state in (TaskState.PENDING, TaskState.READY, TaskState.RUNNING)]
    approved = any(e.type is E.EXPERT_APPROVED for e in deps.dispatcher.store.events())
    return (f"Verified claims: {db.findings.count_documents({'run_id': run})}; refused: {db.refusals.count_documents({'run_id': run})}.\n"
            f"Documents neither read nor excluded: {len(unfinished)}.\n"
            f"Forensic engineer approved: {'yes' if approved else 'no'}.\n"
            f"Open tasks: {len(open_tasks)}; open disputes: {db.disputes.count_documents({'run_id': run, 'status': 'open'})}.\n"
            "Reports received:\n" + ("\n".join(f"- {r.sender.value}: {r.payload.get('summary', '')[:600]}" for r in reports[-6:]) or "(none)"))


def retain(dispatcher: Dispatcher, index: CaseIndex, retention: Retention | None, cause: Event) -> bool:
    """Approve the engineer on the lead's own initiative. Returns False if there is nothing to do."""
    if retention is None or any(e.type is E.EXPERT_APPROVED for e in dispatcher.store.events()):
        return False
    ids = [i for i in retention.document_ids if i in index.documents and not index.documents[i].is_label]
    dispatcher.emit(E.EXPERT_APPROVED, Actor.LEAD, to=Actor.ENGINEER, causation_id=cause.id, subject_ids=ids,
                    payload={"focus": retention.focus, "document_ids": ids, "reason": retention.reason, "initiative": "lead"})
    return True


def _exclude(deps: TeamDeps, exclusions: list[Exclusion], cause: Event) -> None:
    for x in exclusions:
        ids = [i for i in x.document_ids if i in deps.index.documents and not deps.index.documents[i].is_label]
        for i in ids:
            deps.store.db.exclusions.update_one({"_id": f"{deps.store.run_id}:{i}"},
                                                {"$set": {"run_id": deps.store.run_id, "document_id": i, "reason": x.reason}}, upsert=True)
        if ids:
            deps.dispatcher.emit(E.SCOPE_EXCLUDED, Actor.LEAD, subject_ids=ids, causation_id=cause.id, payload={"reason": x.reason})


def _assign(deps: TeamDeps, assignments: list[Assignment], cause: Event) -> list[str]:
    approved = any(e.type is E.EXPERT_APPROVED for e in deps.dispatcher.store.events())
    notes = []
    for a in assignments:
        role = Actor.ENGINEER if a.role.strip().lower().startswith("eng") else Actor.COUNSEL
        if role is Actor.ENGINEER and not approved:
            notes.append("engineer assignment dropped: not approved")
            continue
        ids = [i for i in a.document_ids if i in deps.index.documents and not deps.index.documents[i].is_label]
        if ids:
            deps.dispatcher.emit(E.WORK_ASSIGNED, Actor.LEAD, to=role, causation_id=cause.id, subject_ids=ids,
                                 payload={"document_ids": ids, "focus": a.focus})
    return notes


def can_close(deps: TeamDeps, own_task_id: str) -> tuple[bool, str]:
    db, run = deps.store.db, deps.store.run_id
    unfinished = context.unfinished_documents(db, run, deps.index)
    others = [t for t in deps.dispatcher.store.tasks()
              if t.id != own_task_id and t.state in (TaskState.PENDING, TaskState.READY, TaskState.RUNNING)]
    disputes = db.disputes.count_documents({"run_id": run, "status": "open"})
    if unfinished:
        return False, f"{len(unfinished)} documents neither read nor excluded"
    if others:
        return False, f"{len(others)} tasks still open"
    if disputes:
        return False, f"{disputes} disputes open"
    return True, "ready"


def handle(deps: TeamDeps, event: Event, task_id: str) -> str:
    db, run, gate = deps.store.db, deps.store.run_id, deps.gate
    index = context.document_index(db, run, deps.index)

    if event.type is E.CLAIM_FILE_OPENED:
        out, _ = gate.call(actor="lead", purpose="open", schema=Opening, task_id=task_id, prompt=(
            f"{BRIEF}\n\nA construction-defect claim file has arrived. Assign defense counsel with a first focus. You may "
            f"exclude documents that need not be read in full, with a reason. {RETAIN}\n\nDocument index (id | type | date | from -> to | "
            f"pages | read by):\n{index}"))
        _exclude(deps, out.exclusions, event)
        retain(deps.dispatcher, deps.index, out.retain_engineer, event)
        deps.dispatcher.emit(E.COUNSEL_ASSIGNED, Actor.LEAD, to=Actor.COUNSEL, causation_id=event.id,
                             payload={"focus": out.counsel_focus, "thinking": out.thinking})
        return "counsel assigned"

    if event.type is E.EXPERT_REQUESTED:
        out, _ = gate.call(actor="lead", purpose="expert", schema=ExpertDecision, task_id=task_id, prompt=(
            f"{BRIEF}\n\nDefense counsel asks your approval to retain a forensic engineer with this scope: "
            f"{event.payload.get('scope', '')}\n\n{_state(deps)}\n\nDocument index:\n{index}"))
        if out.approve:
            ids = [i for i in out.document_ids if i in deps.index.documents]
            deps.dispatcher.emit(E.EXPERT_APPROVED, Actor.LEAD, to=Actor.ENGINEER, correlation_id=event.correlation_id,
                                 causation_id=event.id, subject_ids=ids, payload={"focus": out.focus, "document_ids": ids, "reason": out.reason})
            return "expert approved"
        deps.dispatcher.emit(E.EXPERT_DECLINED, Actor.LEAD, to=Actor.COUNSEL, correlation_id=event.correlation_id,
                             causation_id=event.id, payload={"reason": out.reason})
        return "expert declined"

    if event.type is E.DISPUTE_OPENED:
        ids = event.subject_ids
        claims = list(db.findings.find({"_id": {"$in": ids}}))
        listing = "\n".join(f"- {c['_id']} ({c['role']}): {c.get('date')} | {c['statement']} | quote: "
                            f"\"{c['citations'][0]['quote'] if c.get('citations') else ''}\"" for c in claims)
        out, _ = gate.call(actor="lead", purpose="rule", schema=Ruling, task_id=task_id, prompt=(
            f"{BRIEF}\n\nTwo members of your team disagree: {event.payload.get('question', '')}\nTheir verified claims:\n"
            f"{listing}\n\nRule which claim the record supports better, citing the quotes."))
        favoured = out.favoured_claim_id if out.favoured_claim_id in ids else None
        db.disputes.update_one({"_id": event.payload.get("dispute_id")},
                               {"$set": {"status": "ruled", "favoured": favoured, "ruling": out.ruling}})
        deps.dispatcher.emit(E.DISPUTE_RULED, Actor.LEAD, correlation_id=event.correlation_id, causation_id=event.id,
                             subject_ids=ids, payload={"favoured": favoured, "ruling": out.ruling,
                                                       "valid": favoured is not None})
        return "dispute ruled"

    # report.submitted, task.expired, guard.hit: decide what happens next.
    unfinished = context.unfinished_documents(db, run, deps.index)
    out, _ = gate.call(actor="lead", purpose="next", schema=NextStep, task_id=task_id, prompt=(
        f"{BRIEF}\n\nWhat woke you: {event.type.value} from {event.sender.value}: {str(event.payload)[:800]}\n\n{_state(deps)}\n\n"
        f"Assign unread documents to the right role, exclude those that need no full reading (with a reason), or close "
        f"the claim file when everything is read or excluded and nothing is open. {RETAIN}\n\nDocuments not yet read or excluded:\n"
        f"{context.document_index(db, run, deps.index, only=set(unfinished))}"))
    _exclude(deps, out.exclusions, event)
    retained = retain(deps.dispatcher, deps.index, out.retain_engineer, event)  # before assignments, so engineer work is not dropped
    notes = (["engineer retained"] if retained else []) + _assign(deps, out.assignments, event)
    if out.close:
        ok, why = can_close(deps, task_id)
        if ok:
            brief, _ = gate.call(actor="lead", purpose="brief", schema=Brief, task_id=task_id, prompt=(
                f"{BRIEF}\n\nWrite the case brief from the team's verified claims: facts only, citing claim ids.\n\n"
                f"{_state(deps)}\n\nVerified claims (id | kind | date | statement):\n"
                + "\n".join(f"{c['_id']} | {c['kind']} | {c.get('date') or ''} | {c['statement'][:140]}"
                            for c in db.findings.find({"run_id": run}).sort("date", 1).limit(300))))
            known = [c["_id"] for c in db.findings.find({"run_id": run, "_id": {"$in": brief.key_claim_ids}}, {"_id": 1})]
            deps.dispatcher.emit(E.BRIEF_SUBMITTED, Actor.LEAD, causation_id=event.id, subject_ids=known, payload={"summary": brief.summary})
            deps.dispatcher.emit(E.CLAIM_FILE_CLOSED, Actor.LEAD, causation_id=event.id, payload={"reason": out.thinking})
            return "claim file closed"
        notes.append(f"close refused: {why}")
    return "; ".join(notes) or "next steps issued"
