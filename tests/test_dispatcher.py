"""The dispatcher decides what runs when. It is written against these tests before any role exists."""

import pytest

from casefile.team.dispatcher import Dispatcher, NotAllowed, TaskState
from casefile.team.events import Actor, Event, EventType as E, WaitFor
from casefile.team.store import MemoryStore


def ev(type_, sender, to=None, corr="c1", **kw) -> Event:
    return Event(case_id="C", run_id="r", type=type_, sender=sender, to=to, correlation_id=corr, **kw)


@pytest.fixture
def d() -> Dispatcher:
    return Dispatcher(MemoryStore(), case_id="C", run_id="r", max_running=2, deadline_cycles=3)


def test_an_event_wakes_the_role_it_is_addressed_to(d):
    d.publish(ev(E.COUNSEL_ASSIGNED, Actor.LEAD, to=Actor.COUNSEL))
    tasks = d.cycle()
    assert [(t.role, t.state) for t in tasks] == [(Actor.COUNSEL, TaskState.RUNNING)]


def test_duplicate_delivery_does_not_create_a_second_task(d):
    e = ev(E.COUNSEL_ASSIGNED, Actor.LEAD, to=Actor.COUNSEL)
    d.publish(e)
    d.publish(e)  # same id: at-least-once delivery
    d.cycle()
    d.cycle()
    assert len(d.store.tasks()) == 1
    assert len(d.store.events()) == 1


def test_a_role_may_publish_only_its_own_events(d):
    with pytest.raises(NotAllowed, match="engineer may not publish expert.approved"):
        d.publish(ev(E.EXPERT_APPROVED, Actor.ENGINEER, to=Actor.ENGINEER))


def test_task_waits_until_its_dependency_exists(d):
    t = d.create_task(Actor.ENGINEER, "first reading", waits_for=[WaitFor(type=E.EXPERT_APPROVED, correlation_id="c9")])
    d.cycle()
    assert d.store.task(t.id).state is TaskState.PENDING
    d.publish(ev(E.EXPERT_APPROVED, Actor.LEAD, to=Actor.COUNSEL, corr="other"))  # wrong conversation
    d.cycle()
    assert d.store.task(t.id).state is TaskState.PENDING
    d.publish(ev(E.EXPERT_APPROVED, Actor.LEAD, to=Actor.COUNSEL, corr="c9"))
    d.cycle()
    assert d.store.task(t.id).state is TaskState.RUNNING


def test_a_dependency_nobody_can_publish_is_rejected(d):
    # READER_FINISHED is published only by the system; make a spec gap by asking for an event type no role publishes.
    from casefile.team import spec
    original = spec.SPECS[spec.Actor.SYSTEM]
    spec.SPECS[spec.Actor.SYSTEM] = original.model_copy(update={"publishes": frozenset({E.CLAIM_FILE_OPENED})})
    try:
        with pytest.raises(NotAllowed, match="no role publishes reader.finished"):
            d.create_task(Actor.COUNSEL, "wait forever", waits_for=[WaitFor(type=E.READER_FINISHED)])
    finally:
        spec.SPECS[spec.Actor.SYSTEM] = original


def test_no_more_than_max_running_at_once(d):
    for i in range(3):
        d.publish(ev(E.WORK_ASSIGNED, Actor.LEAD, to=Actor.COUNSEL, corr=f"w{i}"))
    d.cycle()
    running = [t for t in d.store.tasks() if t.state is TaskState.RUNNING]
    ready = [t for t in d.store.tasks() if t.state is TaskState.READY]
    assert len(running) == 2 and len(ready) == 1
    d.finish(running[0].id)
    d.cycle()
    assert len([t for t in d.store.tasks() if t.state is TaskState.RUNNING]) == 2


def test_a_task_past_its_deadline_expires_and_the_lead_is_told(d):
    t = d.create_task(Actor.ENGINEER, "waits for approval", waits_for=[WaitFor(type=E.EXPERT_APPROVED, correlation_id="c9")])
    for _ in range(4):
        d.cycle()
    assert d.store.task(t.id).state is TaskState.EXPIRED
    told = [e for e in d.store.events() if e.type is E.TASK_EXPIRED]
    assert len(told) == 1 and told[0].to is Actor.LEAD and told[0].subject_ids == [t.id]
    # the lead is woken by it
    assert any(x.role is Actor.LEAD for x in d.store.tasks())


def test_broadcast_events_wake_every_subscriber(d):
    d.publish(ev(E.DISPUTE_RULED, Actor.LEAD, to=None))
    roles = sorted(t.role.value for t in d.cycle())
    assert roles == ["counsel", "engineer"]
