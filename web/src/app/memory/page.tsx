import { BarChart, LineChart } from "@/components/charts";
import { EvidenceHost, OpenEvidence } from "@/components/EvidenceHost";
import { loadBundle, lookupFor } from "@/lib/data";

export default function MemoryPage() {
  const b = loadBundle();
  const progress = b.trace.filter((t) => t.kind === "progress");
  const decisions = b.trace.filter((t) => (t.kind === "decision" || t.kind === "rejected") && t.context_chars);
  const docs = b.documents.filter((d) => !d.is_label);
  const readCount = docs.filter((d) => d.read_by.length > 0).length;
  const both = docs.filter((d) => d.read_by.length > 1).length;
  const parties = docs.filter((d) => d.read_by.length === 1 && d.read_by[0].startsWith("parties")).length;
  const technical = docs.filter((d) => d.read_by.length === 1 && d.read_by[0].startsWith("technical")).length;
  const refusals = b.refusals.filter((r) => r.kind !== "negative");
  const tokens = b.workers.reduce((a, w) => a + w.prompt_tokens + w.output_tokens + w.thinking_tokens, 0);
  return (
    <EvidenceHost claims={Object.fromEntries(refusals.map((c) => [c.id, c]))} lookup={lookupFor(b, refusals)}>
      <div className="page">
        <div className="page-head">
          <div className="eyebrow">What the run knew, and when</div>
          <h1>Memory</h1>
          <p>The run keeps nothing important in the model&apos;s prompt. Coverage, verified findings and refusals are written to MongoDB as they happen, and the examiner&apos;s context is rebuilt from them each turn.</p>
        </div>

        <section className="section">
          <h2>Coverage of the claim file</h2>
          <p>{readCount} of {docs.length} documents read ({b.coverage.pages_read.toLocaleString()} of {b.coverage.pages_total.toLocaleString()} pages): {both} by both reviewers, {parties} by the parties reviewer only, {technical} by the technical reviewer only. {b.case.withheld.length} source PDFs the NTSB wrote as its own analysis are withheld by design.</p>
          <div className="card pad" style={{ display: "grid", gap: 10 }}>
            <div className="covmap" role="img" aria-label={`${readCount} of ${docs.length} documents read`}>
              {docs.map((d) => (
                <span key={d.id} className={`cov${d.read_by.length ? " read" : ""}${d.read_by.length > 1 ? " both" : ""}`}
                      title={`${d.id.split(":").slice(1).join(" ")} · ${d.doc_type.replaceAll("_", " ")}${d.date ? ` · ${d.date}` : ""} · ${d.page_ids.length} pages · ${d.read_by.length ? `read by ${d.read_by.map((r) => r.split("_")[0]).join(" and ")}` : "not read"}`} />
              ))}
            </div>
            <div className="legend-row">
              <span><i className="cov read both" /> read by both</span>
              <span><i className="cov read" /> read by one reviewer</span>
              <span><i className="cov" /> not read</span>
              <span style={{ color: "var(--muted)" }}>One square per document, in source PDF order. Hover for details.</span>
            </div>
          </div>
        </section>

        <section className="section">
          <h2>Growth, turn by turn</h2>
          <div className="grid-2">
            <LineChart title="Pages read" points={progress.map((t) => ({ x: t.turn + 1, y: t.coverage_pages ?? 0, label: `Turn ${t.turn + 1}: ${t.coverage_pages} pages read` }))} />
            <LineChart title="Verified claims" points={progress.map((t) => ({ x: t.turn + 1, y: t.verified_total ?? 0, label: `Turn ${t.turn + 1}: ${t.verified_total} verified, ${t.refused_total} refused` }))} />
          </div>
          <div className="grid-2">
          <BarChart
            title="Examiner's context each turn"
            points={decisions.map((t) => ({ x: t.turn + 1, y: t.context_chars ?? 0, label: `Turn ${t.turn + 1}: ${(t.context_chars ?? 0).toLocaleString()} characters` }))}
            fmt={(v) => `${Math.round(v / 1000)}k`}
            note="Characters in the examiner's prompt each turn."
          />
          <div className="card pad" style={{ display: "grid", gap: 8, alignContent: "start", fontSize: 13 }}>
            <strong>Why the context stays bounded</strong>
            <span>The examiner never sees page text. Its prompt is rebuilt from MongoDB each turn: the document list, progress, the newest open questions and refusals. It grows with the length of those lists, not with the number of pages read.</span>
            <span style={{ color: "var(--muted)" }}>Readers see page text, but each reads only its own batch of about 25 pages and ends.</span>
          </div>
          </div>
        </section>

        <section className="section">
          <h2>Refusals <span className="num" style={{ color: "var(--muted)", fontWeight: 400 }}>({refusals.length})</span></h2>
          <p>Claims the verifier would not accept, with its reasons. Each can be sent back for repair once.</p>
          <div className="card table-wrap">
            <table className="data">
              <thead><tr><th>Claim</th><th>Reason</th><th>Repair</th></tr></thead>
              <tbody>
                {refusals.map((r) => (
                  <tr key={r.id}>
                    <td><OpenEvidence className="row-open" claimIds={[r.id]} title={r.statement} eyebrow="Refused claim"><span className="row-title">{r.statement}</span></OpenEvidence></td>
                    <td style={{ color: "var(--muted)" }}>{r.reasons[0]}</td>
                    <td>{r.repair_attempted ? <span className="pill neutral">attempted</span> : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="section">
          <h2>Absences</h2>
          {b.negatives.length ? (
            <ul>{b.negatives.map((n) => <li key={n}>{n}</li>)}</ul>
          ) : (
            <div className="empty">No absences yet. They are proposed after the loop ends, and this run stopped before that step.</div>
          )}
        </section>

        <section className="section">
          <h2>Readers</h2>
          <p>{b.workers.length} readers started, {tokens.toLocaleString()} tokens in total (prompt, output and thinking).</p>
        </section>
      </div>
    </EvidenceHost>
  );
}
