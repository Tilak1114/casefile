"""Who may publish and who wakes on each event: the team's rules, enforced by the dispatcher."""

from pydantic import BaseModel, ConfigDict

from casefile.team.events import Actor, EventType as E


class RoleSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    actor: Actor
    wakes_on: frozenset[E]  # events that start a task for this role when addressed to it (or broadcast)
    publishes: frozenset[E]  # the only events this role may append


SPECS: dict[Actor, RoleSpec] = {
    Actor.LEAD: RoleSpec(
        actor=Actor.LEAD,
        wakes_on=frozenset({E.CLAIM_FILE_OPENED, E.EXPERT_REQUESTED, E.REPORT_SUBMITTED, E.DISPUTE_OPENED,
                            E.POSITION_SUBMITTED, E.TASK_EXPIRED, E.GUARD_HIT}),
        publishes=frozenset({E.COUNSEL_ASSIGNED, E.EXPERT_APPROVED, E.EXPERT_DECLINED, E.WORK_ASSIGNED,
                             E.DISPUTE_RULED, E.CLAIM_FILE_CLOSED, E.BRIEF_SUBMITTED}),
    ),
    Actor.COUNSEL: RoleSpec(
        actor=Actor.COUNSEL,
        wakes_on=frozenset({E.COUNSEL_ASSIGNED, E.WORK_ASSIGNED, E.REQUEST_RAISED, E.EXPERT_DECLINED,
                            E.DISPUTE_RULED}),
        publishes=frozenset({E.EXPERT_REQUESTED, E.REQUEST_RAISED, E.REQUEST_ANSWERED, E.DISPUTE_OPENED,
                             E.POSITION_SUBMITTED, E.REPORT_SUBMITTED, E.ABSENCE_PROPOSED}),
    ),
    Actor.ENGINEER: RoleSpec(
        actor=Actor.ENGINEER,
        wakes_on=frozenset({E.EXPERT_APPROVED, E.WORK_ASSIGNED, E.REQUEST_RAISED, E.DISPUTE_RULED}),
        publishes=frozenset({E.REQUEST_RAISED, E.REQUEST_ANSWERED, E.DISPUTE_OPENED, E.POSITION_SUBMITTED,
                             E.REPORT_SUBMITTED, E.ABSENCE_PROPOSED}),
    ),
    # Code components: they publish what they compute; they are not woken as model tasks.
    Actor.SYSTEM: RoleSpec(actor=Actor.SYSTEM, wakes_on=frozenset(), publishes=frozenset({E.CLAIM_FILE_OPENED, E.READER_FINISHED})),
    Actor.VERIFIER: RoleSpec(actor=Actor.VERIFIER, wakes_on=frozenset(),
                             publishes=frozenset({E.CLAIM_VERIFIED, E.CLAIM_REFUSED, E.DISPUTE_RULED, E.ABSENCE_CHECKED})),
    Actor.DISPATCHER: RoleSpec(actor=Actor.DISPATCHER, wakes_on=frozenset(), publishes=frozenset({E.TASK_EXPIRED, E.GUARD_HIT})),
    Actor.ASSEMBLY: RoleSpec(actor=Actor.ASSEMBLY, wakes_on=frozenset(), publishes=frozenset()),
}

MODEL_ROLES = (Actor.LEAD, Actor.COUNSEL, Actor.ENGINEER)


def publishable(event_type: E) -> bool:
    """Some role in the team can publish this event, so waiting for it can succeed."""
    return any(event_type in s.publishes for s in SPECS.values())
