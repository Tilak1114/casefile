"""Start or resume a run, then close it: negatives, outputs, and a final trace event."""

from datetime import UTC, datetime
from uuid import uuid4

from langgraph.checkpoint.mongodb import MongoDBSaver

from casefile import db as dbmod
from casefile.case import CaseConfig
from casefile.config import DATA_DIR, settings
from casefile.harness.assemble import RunOutputs, assemble, propose_and_check_negatives
from casefile.harness.examiner import Deps
from casefile.harness.graph import build_graph, run_config
from casefile.harness.models import RunState, TraceKind
from casefile.harness.store import RunStore
from casefile.models.gemini import Gemini
from casefile.sources.models import FetchManifest
from casefile.verify.coverage import CoverageLog
from casefile.verify.load import load_index


def run_case(case_id: str, run_id: str | None = None, allow_spend: bool = False) -> RunOutputs:
    config = settings()
    client = dbmod.client()
    db = client[config.casefile_database]
    case_dir = DATA_DIR / "cases" / case_id
    case = CaseConfig.model_validate_json((case_dir / "case.json").read_text())
    manifest = FetchManifest.model_validate_json((case_dir / "fetch_manifest.json").read_text())
    run_id = run_id or f"run-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
    deps = Deps(
        gemini=Gemini(config.gemini_token, config.gemini_model or "", case_dir / "cache" / "gemini", allow_spend=allow_spend),
        index=load_index(db, case_id), store=RunStore(db, case_id, run_id), coverage=CoverageLog(db, case_id, run_id),
    )
    checkpointer = MongoDBSaver(client, db_name=config.casefile_database)
    graph = build_graph(deps, checkpointer)
    cfg = run_config(run_id)
    resuming = checkpointer.get_tuple(cfg) is not None
    if not resuming:
        deps.store.trace(0, TraceKind.RUN_START, f"run {run_id} on {case_id}: {len(deps.index.documents)} documents")
    final = graph.invoke(None if resuming else RunState(run_id=run_id, case_id=case_id), cfg)
    state = RunState.model_validate(final)
    accepted, refused = propose_and_check_negatives(deps, state.turn)
    outputs = assemble(deps, case, {f.file_no: f.sha256 for f in manifest.files})
    deps.store.trace(state.turn, TraceKind.RUN_END,
                     f"{state.stop_reason}; negatives {accepted} accepted, {refused} refused; "
                     f"{len(outputs.chronology)} chronology entries, {len(outputs.parties)} parties",
                     coverage_pages=outputs.coverage.pages_read, verified_total=deps.store.count("findings"),
                     refused_total=deps.store.count("refusals"))
    return outputs
