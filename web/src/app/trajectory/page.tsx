import { LineChart } from "@/components/charts";
import { Trajectory, type DocInfo, type Stage } from "@/components/Trajectory";
import { loadBundle } from "@/lib/data";
import { clock } from "@/lib/time";

export default function TrajectoryPage() {
  const b = loadBundle();
  const team = b.team;
  if (!team) {
    return (
      <div className="page">
        <div className="page-head"><div className="eyebrow">Trajectory</div><h1>No team run in this export</h1></div>
        <div className="empty">Run {b.run.run_id} was made by the v1 examiner. Its turns are on the Harness screen.</div>
      </div>
    );
  }
  const ev = (t: string) => team.events.filter((e) => e.type === t);
  const docs: Record<string, DocInfo> = Object.fromEntries(b.documents.map((d) => [d.id, { doc_type: d.doc_type, date: d.date ?? null, file_no: d.file_no, pages: d.page_ids.length }]));
  const last = team.series[team.series.length - 1];
  const opened = ev("claim_file.opened")[0];
  const closed = ev("claim_file.closed")[0];
  const reassigned = ev("work.assigned");
  const checked = ev("absence.checked");
  const stages: Stage[] = [
    { key: "open", title: "Open", detail: opened?.summary ?? "", types: ["claim_file.opened"] },
    { key: "plan", title: "Plan the work", detail: `${team.exclusions.length} documents excluded · engineer ${ev("expert.approved").length ? "retained" : "not retained"} · counsel assigned`, types: ["scope.excluded", "counsel.assigned", "expert.approved", "expert.requested"] },
    { key: "read", title: "Read in parallel", detail: `${team.readers.length} readers · ${last.pages.toLocaleString()} pages`, types: ["reader"] },
    { key: "verify", title: "Verify every claim", detail: `${last.verified.toLocaleString()} kept · ${last.refused} refused`, types: ["reader"] },
    { key: "report", title: "Report", detail: `${ev("report.submitted").length} reports to the lead`, types: ["report.submitted"] },
    { key: "reassign", title: "Reassign", detail: `${reassigned.length} assignments · ${reassigned.reduce((a, e) => a + e.subjects, 0)} documents`, types: ["work.assigned"] },
    { key: "close", title: "Close", detail: `${ev("guard.hit").length} guard · closed at ${closed ? clock(closed.t) : "—"}`, types: ["guard.hit", "brief.submitted", "claim_file.closed"] },
    { key: "absences", title: "Absences", detail: `${ev("absence.proposed").length} proposed · ${checked.filter((e) => e.summary === "verified").length} kept`, types: ["absence.proposed", "absence.checked"] },
    { key: "assemble", title: "Assemble", detail: `${b.chronology.length} chronology entries · ${b.parties.length} parties · ${b.exhibits.length} exhibits`, types: [] },
  ];
  const step = Math.max(1, Math.floor(team.series.length / 80));
  const pts = team.series.filter((_, i) => i % step === 0 || i === team.series.length - 1);
  const minutes = (x: number) => clock(x);
  return (
    <div className="page" style={{ maxWidth: 1400 }}>
      <div className="page-head">
        <div className="eyebrow">Run {b.run.run_id} · as it happened</div>
        <h1>Trajectory</h1>
        <p>
          Every step the team took, read back from the MongoDB event log. The claim professional never reads pages; it assigns work,
          retains the engineer and closes the file. Counsel and the engineer work in parallel through readers, and every claim is checked
          against the page before it counts. {clock(team.duration_s)} end to end, {team.calls} model calls, ${team.cost_usd.toFixed(2)}, stopped because: {team.stop_reason}.
        </p>
      </div>

      <Trajectory team={team} docs={docs} stages={stages} />

      <section className="section">
        <h2>Progress over the run</h2>
        <div className="grid-3">
          <LineChart title="Distinct pages given to readers" xFmt={minutes} points={pts.map((p) => ({ x: p.t, y: p.pages, label: `${clock(p.t)}: ${p.pages} pages` }))} />
          <LineChart title="Verified claims" xFmt={minutes} points={pts.map((p) => ({ x: p.t, y: p.verified, label: `${clock(p.t)}: ${p.verified} verified, ${p.refused} refused` }))} />
          <LineChart title="Model cost (USD)" xFmt={minutes} fmt={(v) => `$${v.toFixed(2)}`} points={pts.map((p) => ({ x: p.t, y: p.cost_usd, label: `${clock(p.t)}: $${p.cost_usd.toFixed(2)}` }))} />
        </div>
        <p style={{ fontSize: 12, color: "var(--muted)" }}>Pages are counted when the harness hands them to a reader, before the model runs. Cost is what OpenRouter reported for each call.</p>
      </section>

      {team.exclusions.length > 0 && (
        <section className="section">
          <h2>Excluded by the lead, with its reason</h2>
          <div className="card table-wrap">
            <table className="data">
              <thead><tr><th>Document</th><th>Type</th><th>Pages</th><th>Reason</th></tr></thead>
              <tbody>
                {team.exclusions.map((x) => (
                  <tr key={x.document_id}>
                    <td className="mono" style={{ whiteSpace: "nowrap" }}>PDF {x.document_id.split(":")[1]} · {x.document_id.split(":")[2]}</td>
                    <td>{docs[x.document_id]?.doc_type.replaceAll("_", " ")}</td>
                    <td className="num">{docs[x.document_id]?.pages}</td>
                    <td>{x.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
