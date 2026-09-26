"""The v2 team for the Harness screen, read from the code that runs it: roles and their subscriptions from
`team.spec`, briefs from `team.roles` and `team.lead`, guards from the modules' constants."""

import inspect

from casefile.export.models import EventSpecRow, TeamMember, TeamSpec
from casefile.harness import examiner
from casefile.team import lead, reader, reviewer, run
from casefile.team.dispatcher import Dispatcher
from casefile.team.events import Actor, EventType
from casefile.team.llm import MAX_MODEL_CALLS_AT_ONCE
from casefile.team.roles import COUNSEL, ENGINEER
from casefile.team.spec import SPECS

VERIFIER_RULES = [
    "Every quote must be found on the page it cites. Whitespace, curly quotes and dashes are folded, and a word may be "
    "joined across a hyphen at a line break; case, spelling and word order must match.",
    "A quote on a production label (a cover sheet or divider added when the claim file was assembled), or on a page "
    "outside the readable claim file, is refused.",
    "An event dated as the document's own date must match the date read from the document; an event dated from the "
    "text must have a quote that shows that date.",
    "A party's name must appear in its quotes, ignoring case, punctuation and corporate suffixes; a relationship's two "
    "parties must both appear. At assembly, a name also appears through a verified alias quoted in the claim.",
    "An alias is accepted only when one quote shows both names.",
    "A refused claim is sent back to its reader once with the page and the reason; if it still fails it is kept with "
    "its reasons, never softened.",
]
NEGATIVE_RULE = ("At the end, each role proposes what the claim file does not contain, with search terms that would "
                 "find a counter-example. An absence is accepted only if every in-scope page was read in the run and a "
                 "phrase search for each term finds nothing in scope.")
MEMORY = {
    "events": "the append-only event log: every message between roles, with its cause; change streams wake consumers",
    "tasks": "one task per event a role must handle: waits-for, deadline, state, outcome",
    "reservations": "which task holds which document, per role (unique index), so no document is read twice by a role",
    "coverage": "every page handed to a reader, with the role and focus, logged before the model runs",
    "findings / refusals": "verified claims, and refused ones with the verifier's reasons",
    "disputes": "conflicting claims on the same page and the lead's ruling",
    "model_calls": "every model call: who, for which task, tokens, cost, the decision and its reasoning summary",
    "workers": "every reader: documents, pages, focus, claims kept and refused",
    "checkpoints": "LangGraph state of each role's task (plan, read, review, close), so a task can resume",
    "pages / documents / metadata / sources": "the ingested claim file (GridFS for the PDFs, Atlas Search on page text)",
    "cache": "model and parser answers, so a finished run replays for free",
}


DEADLINE_CYCLES = inspect.signature(Dispatcher.__init__).parameters["deadline_cycles"].default


def _events(types) -> list[str]:
    return sorted(t.value for t in types)


def team_spec() -> TeamSpec:
    lead_spec, counsel_spec, engineer_spec = SPECS[Actor.LEAD], SPECS[Actor.COUNSEL], SPECS[Actor.ENGINEER]
    members = [
        TeamMember(
            actor="lead", title="Claim professional", kind="model",
            mirrors="the carrier's claim professional who owns the claim file",
            job=lead.BRIEF + " It cannot exclude documents: every document is read by some role.", sees="the document index (type, date, author, recipient, pages, who read it), counts of "
            "verified and refused claims, open tasks and disputes, reports received. Never page text.",
            can=["assign counsel and work, with a focus", "retain the forensic engineer, on request or on its own initiative",
                 "rule disputes citing claim ids",
                 "close the claim file (only when the code's close check passes)", "write the case brief from verified claims"],
            never="reads pages, makes claims about their content, states fault or coverage",
            wakes_on=_events(lead_spec.wakes_on), publishes=_events(lead_spec.publishes), waits_for="nothing"),
        TeamMember(
            actor="counsel", title=COUNSEL.title, kind="model", mirrors="panel defense counsel",
            job=COUNSEL.brief, sees="the document index, its own verified claims and open questions; page text only through its readers",
            can=["plan what to read and start readers", "review its readers' claims and read more (up to "
                 f"{reviewer.MAX_FOLLOW_UP_ROUNDS} follow-up rounds)", "ask the lead to retain an engineer",
                 "raise and answer requests, open disputes", "report to the lead", "propose absences"],
            never="retains the engineer without approval; states fault",
            wakes_on=_events(counsel_spec.wakes_on), publishes=_events(counsel_spec.publishes), waits_for="nothing"),
        TeamMember(
            actor="engineer", title=ENGINEER.title, kind="model", mirrors="the forensic expert retained with the carrier's approval",
            job=ENGINEER.brief, sees="as counsel, for its own documents and claims",
            can=["as counsel, except asking for an expert"], never="gives an opinion on cause",
            wakes_on=_events(engineer_spec.wakes_on), publishes=_events(engineer_spec.publishes),
            waits_for="expert.approved: it cannot start before the lead approves it"),
        TeamMember(
            actor="readers", title="Readers", kind="model", mirrors="the reading a person does",
            job="Read whole documents (long ones in page windows) for one role and focus; return dated events, parties, "
            "relationships, aliases and open questions, each with an exact quote.",
            sees=f"only their batch (about {examiner.MAX_CHARS_PER_READER // 1000}k characters), plus up to "
            f"{reader.MAX_ATTACHED_REFERENCES} short documents it cites by reference number",
            can=["return quoted claims", "one automatic repair of refused claims"], never="decide what to read next",
            wakes_on=[], publishes=[], waits_for="started by a role's task"),
        TeamMember(
            actor="harness", title="Dispatcher, verifier, assembly", kind="code", mirrors="the claims system and file rules",
            job="Turns events into tasks and runs them in parallel; checks every claim against the page; tests absences; "
            "decides whether the file may close; assembles the chronology, party map and exhibits.",
            sees="everything in MongoDB", can=["enforce who may publish what", "hold a task until what it waits for exists",
                                               "expire stuck tasks and tell the lead", "stop the run on a guard"],
            never="uses a model", wakes_on=[], publishes=_events(SPECS[Actor.DISPATCHER].publishes | SPECS[Actor.VERIFIER].publishes
                                                                  | SPECS[Actor.SYSTEM].publishes), waits_for="—"),
    ]
    events = [EventSpecRow(type=t.value, published_by=sorted(a.value for a, s in SPECS.items() if t in s.publishes),
                           wakes=sorted(a.value for a, s in SPECS.items() if t in s.wakes_on)) for t in EventType]
    guards = {
        "tasks running at once": run.MAX_TASKS_AT_ONCE, "model calls at once": MAX_MODEL_CALLS_AT_ONCE,
        "task deadline (dispatcher cycles)": DEADLINE_CYCLES,
        "cycles without progress before the lead is told": run.STALL_CYCLES, "tokens per run": run.MAX_RUN_TOKENS,
        "documents per reading round": reviewer.MAX_DOCUMENTS_PER_ROUND, "follow-up rounds per task": reviewer.MAX_FOLLOW_UP_ROUNDS,
        "characters per reader": examiner.MAX_CHARS_PER_READER, "pages per reader": examiner.PAGES_PER_READER,
        "referenced documents attached per reader": reader.MAX_ATTACHED_REFERENCES,
        "largest attached document (pages)": reader.MAX_ATTACHED_PAGES,
        "repairs per refused claim": 1,
    }
    return TeamSpec(members=members, events=events, guards=guards, verifier_rules=VERIFIER_RULES,
                    negative_rule=NEGATIVE_RULE, memory=MEMORY)
