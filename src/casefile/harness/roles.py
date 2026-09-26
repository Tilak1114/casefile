"""The standing roles. Each mirrors a job on a liability-side claims team (docs/00-process-today.md)."""

from pydantic import BaseModel, ConfigDict

from casefile.harness.models import Role


class RoleSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    title: str
    mirrors: str
    brief: str
    default_focus: str


ROLES: dict[Role, RoleSpec] = {
    Role.PARTIES: RoleSpec(
        role=Role.PARTIES,
        title="Parties reviewer",
        mirrors="defense counsel mapping parties and contractor tiers from the records",
        brief="You are the parties reviewer on a construction claim. You work out, from the records only, "
        "who the parties are, what role each had on the project, and how they are related: who contracted "
        "with whom, who represented whom, who reviewed whose submittals, who supplied what, who inspected.",
        default_focus="every organisation and person named, their roles, the relationships between them, "
        "and names written differently for the same party",
    ),
    Role.TECHNICAL: RoleSpec(
        role=Role.TECHNICAL,
        title="Technical reviewer",
        mirrors="the forensic engineer's document review",
        brief="You are the technical reviewer on a construction claim. You record, from the records only, "
        "the design requirements, submittals and how they were dispositioned, tests and their results, "
        "deviations from requirements, and when each happened. You state facts, never causes.",
        default_focus="dated events: design requirements and values, submittals and approvals, tests and "
        "results, problems reported, repairs, and what the documents do not contain",
    ),
}
