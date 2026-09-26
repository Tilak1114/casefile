"""Score the Claude comparison run with Casefile's own verifier and answer key. No coverage is logged:
the agents read their text files outside the harness, so nothing records which pages they read."""
import glob, json, sys
from casefile import db as dbmod
from casefile.case import CaseConfig
from casefile.config import DATA_DIR, settings
from casefile.harness.assemble import assemble
from casefile.harness.checks import check_output
from casefile.harness.examiner import Deps
from casefile.harness.models import ReaderOutput, Role
from casefile.harness.store import RunStore
from casefile.sources.models import FetchManifest
from casefile.verify.coverage import CoverageLog
from casefile.verify.load import load_index

RUN = "claude-code-1"; C = "HWY06MH024"
S = "data/cases/HWY06MH024/comparisons/claude-code-1"
d = dbmod.client()[settings().casefile_database]
for coll in ("findings", "refusals", "coverage", "workers", "outputs", "pending"):
    d[coll].delete_many({"run_id": RUN})
d.outputs.delete_one({"_id": RUN})
idx = load_index(d, C); store = RunStore(d, C, RUN)
kinds = ("events", "parties", "relationships", "aliases")
files = sorted(glob.glob(f"{S}/out*.json")); dropped = 0
for i, f in enumerate(files):
    raw = json.load(open(f)); items = {}
    for k in kinds:  # keep every item that fits the schema; count the rest
        ok = []
        for it in raw.get(k, []):
            try:
                ReaderOutput.model_validate({k: [it]}); ok.append(it)
            except Exception:
                dropped += 1
        items[k] = ok
    out = ReaderOutput.model_validate(items)
    claims = check_output(out, idx, run_id=RUN, case_id=C, role=Role.COUNSEL, worker_id=f"claude-{i+1}")
    store.save_claims(claims)
case_dir = DATA_DIR / "cases" / C
case = CaseConfig.model_validate_json((case_dir / "case.json").read_text())
manifest = FetchManifest.model_validate_json((case_dir / "fetch_manifest.json").read_text())
assemble(Deps(gemini=None, index=idx, store=store, coverage=CoverageLog(d, C, RUN)), case, {f.file_no: f.sha256 for f in manifest.files})
print("files", len(files), "| schema-invalid items dropped", dropped,
      "| verified", d.findings.count_documents({"run_id": RUN}), "| refused", d.refusals.count_documents({"run_id": RUN}))
