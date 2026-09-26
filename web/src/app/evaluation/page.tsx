import { EvidenceHost, OpenEvidence } from "@/components/EvidenceHost";
import { claimsById, loadBundle, lookupFor, pageLabel } from "@/lib/data";
import type { ScoreRow } from "@/lib/types";

function frac(a: number, b: number) {
  return <span className="num">{a} / {b}</span>;
}

export default function EvaluationPage() {
  const b = loadBundle();
  const claims = claimsById(b);
  const found = b.answer_key.flatMap((k) => k.found_by).map((id) => claims[id]).filter(Boolean);
  type Col = { name: string; s: ScoreRow | null | undefined; pages?: React.ReactNode; readers?: React.ReactNode; cost?: React.ReactNode };
  const cols: Col[] = [
    { name: `Casefile harness · ${b.run.run_id}`, s: b.score, cost: b.team ? <span className="num">${b.team.cost_usd.toFixed(2)}</span> : undefined },
    ...b.comparisons.map((c) => ({ name: c.label, s: c.score, pages: <span style={{ color: "var(--muted)" }}>not recorded</span>,
                                   readers: <span className="num">8 agents</span>, cost: <span style={{ color: "var(--muted)" }}>not metered</span> })),
    { name: "Single prompt · baseline", s: b.baseline },
  ];
  const override: Record<string, keyof Col> = { "Pages read": "pages", "Reading calls (readers started)": "readers", "Cost": "cost" };
  const rows: [string, (s: ScoreRow) => React.ReactNode][] = [
    ["Pages read", (s) => <span className="num">{s.pages_read.toLocaleString()}</span>],
    ["Key events found, development set", (s) => frac(s.dev.events_found, s.dev.events_total)],
    ["  of them on the causal chain", (s) => frac(s.dev.core_found, s.dev.core_total)],
    ["Key events found, held-out set", (s) => frac(s.heldout.events_found, s.heldout.events_total)],
    ["  of them on the causal chain", (s) => frac(s.heldout.core_found, s.heldout.core_total)],
    ["Relationships found", (s) => frac(s.dev.relationships_found + s.heldout.relationships_found, s.dev.relationships_total + s.heldout.relationships_total)],
    ["Parties found", (s) => frac(s.parties_found, s.parties_total)],
    ["Claims verified", (s) => <span className="num">{s.verified_claims}</span>],
    ["Claims refused", (s) => <span className="num">{s.refused_claims} ({Math.round((100 * s.refused_claims) / Math.max(1, s.verified_claims + s.refused_claims))}%)</span>],
    ["Reading calls (readers started)", (s) => <span className="num">{s.readers}</span>],
    ["Cost", (s) => <span className="num">${s.cost_usd.toFixed(2)}</span>],
  ];
  const splits = [["dev", "Development set (used while building)"], ["heldout", "Held-out set (scored only at the end)"]] as const;
  return (
    <EvidenceHost claims={Object.fromEntries(found.map((c) => [c.id, c]))} lookup={lookupFor(b, found)}>
      <div className="page">
        <div className="page-head">
          <div className="eyebrow">Measured against the NTSB&apos;s findings</div>
          <h1>Evaluation</h1>
          <p>The answer key is built from the NTSB final report HAR-07/02 and its six analysis PDFs, which the agent never sees. It is used to score runs and as context, never as a finding of fault. Run {b.run.run_id}: {b.run.status}.</p>
        </div>
        <section className="section">
          <h2>Harness against a single prompt and a general-purpose agent</h2>
          <p>Every column is checked by the same verifier and scored against the same key. The baseline gives every readable page to one Gemini call, the same model the harness uses. {b.comparisons.map((c) => `${c.label}: ${c.note}.`).join(" ")}</p>
          <div className="card table-wrap">
            <table className="data">
              <thead><tr><th></th>{cols.map((c) => <th key={c.name} style={{ textAlign: "right" }}>{c.name}</th>)}</tr></thead>
              <tbody>
                {rows.map(([label, f], i) => (
                  <tr key={`${i}-${label}`}>
                    <td style={{ paddingLeft: label.startsWith("  ") ? 28 : 12, color: label.startsWith("  ") ? "var(--muted)" : undefined }}>{label.trim()}</td>
                    {cols.map((c) => {
                      const o = override[label.trim()];
                      const special = o ? (c[o] as React.ReactNode) : undefined;
                      return <td key={c.name} style={{ textAlign: "right" }}>{special ?? (c.s ? f(c.s) : "—")}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        {splits.map(([split, title]) => {
          const events = b.answer_key.filter((k) => k.split === split);
          return (
            <section key={split} className="section">
              <h2>{title}: {events.filter((e) => e.found_by.length).length} of {events.length} found</h2>
              <div className="card table-wrap">
                <table className="data">
                  <thead><tr><th>Key</th><th>Date</th><th>What the NTSB established</th><th>Chain</th><th>This run</th></tr></thead>
                  <tbody>
                    {events.map((k) => (
                      <tr key={k.id}>
                        <td className="mono">{k.id}</td>
                        <td className="date">{k.date}</td>
                        <td>
                          <div>{k.summary}</div>
                          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>NTSB p.{k.ntsb_page}: “{k.ntsb_quote}” · evidence in {k.evidence_pages.map(pageLabel).join("; ")}</div>
                        </td>
                        <td>{k.core ? <span className="pill accent">causal</span> : <span className="pill neutral">context</span>}</td>
                        <td>
                          {k.found_by.length
                            ? <OpenEvidence claimIds={k.found_by} title={k.summary} eyebrow={`Key event ${k.id} · ${k.date}`}><span className="pill ok">✓ found</span></OpenEvidence>
                            : <span className="pill bad">✕ missed</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })}
      </div>
    </EvidenceHost>
  );
}
