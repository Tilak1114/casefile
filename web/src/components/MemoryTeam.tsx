import { BarChart, LineChart } from "@/components/charts";
import { EvidenceHost, OpenEvidence } from "@/components/EvidenceHost";
import { lookupFor } from "@/lib/data";
import { clock } from "@/lib/time";
import type { Bundle } from "@/lib/types";

type Team = NonNullable<Bundle["team"]>;

export function MemoryTeam({ b, team }: { b: Bundle; team: Team }) {
  const docs = b.documents.filter((d) => !d.is_label);
  const excluded = new Set(team.exclusions.map((x) => x.document_id));
  const state = (d: (typeof docs)[number]) =>
    d.read_by.length > 1 ? "both" : d.read_by[0] === "counsel" ? "counsel" : d.read_by[0] === "engineer" ? "engineer" : excluded.has(d.id) ? "excluded" : "unread";
  const count = (s: string) => docs.filter((d) => state(d) === s).length;
  const refusals = b.refusals.filter((r) => r.kind !== "negative");
  const leadCalls = team.calls.filter((c) => c.actor === "lead");
  const roleCalls = team.calls.filter((c) => c.actor === "counsel" || c.actor === "engineer");
  const leadMax = Math.max(...leadCalls.map((c) => c.prompt_tokens));
  const leadMin = Math.min(...leadCalls.map((c) => c.prompt_tokens));
  const step = Math.max(1, Math.floor(team.series.length / 80));
  const pts = team.series.filter((_, i) => i % step === 0 || i === team.series.length - 1);
  const described: Record<string, string> = {
    events: "messages between roles", tasks: "work items the dispatcher created", reservations: "document holds, per role",
    coverage: "reads: pages handed to readers", findings: "verified claims", refusals: "refused claims, with reasons",
    exclusions: "documents ruled out, with reasons", disputes: "conflicts ruled by the lead", model_calls: "model calls with decision and reasoning",
    workers: "readers started", checkpoints: "LangGraph checkpoints of the roles' tasks",
  };
  return (
    <EvidenceHost claims={Object.fromEntries(refusals.map((c) => [c.id, c]))} lookup={lookupFor(b, refusals)}>
      <div className="page">
        <div className="page-head">
          <div className="eyebrow">What the run knew, and when</div>
          <h1>Memory</h1>
          <p>
            No agent carries the run in its prompt. Everything the team learns is written to MongoDB as it happens, and each agent&apos;s
            context is rebuilt from it for every task: the lead from the document index and counts, counsel and the engineer from their
            own verified claims, readers from their pages alone.
          </p>
        </div>

        <section className="section">
          <h2>What run {b.run.run_id} wrote to MongoDB</h2>
          <div className="stat-grid">
            {Object.entries(team.memory_counts).map(([k, v]) => (
              <div key={k} className="card pad stat">
                <span className="mono stat-k">{k}</span>
                <span className="num stat-v">{v.toLocaleString()}</span>
                <span className="stat-d">{described[k] ?? ""}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="section">
          <h2>Coverage of the claim file</h2>
          <p>
            {docs.length - count("unread") - count("excluded")} of {docs.length} documents read in full ({b.coverage.pages_read.toLocaleString()} of{" "}
            {b.coverage.pages_total.toLocaleString()} pages): {count("both")} by both roles, {count("counsel")} by counsel only, {count("engineer")} by the
            engineer only; {count("excluded")} excluded by the lead with a reason; {count("unread")} unread. The {b.case.withheld.length} NTSB analysis PDFs are
            withheld by design.
          </p>
          <div className="card pad" style={{ display: "grid", gap: 10 }}>
            <div className="covmap" role="img" aria-label={`${count("both")} documents read by both roles, ${count("counsel")} by counsel, ${count("engineer")} by the engineer, ${count("excluded")} excluded, ${count("unread")} unread`}>
              {docs.map((d) => (
                <span key={d.id} className={`cov cov-${state(d)}`}
                      title={`${d.id.split(":").slice(1).join(" ")} · ${d.doc_type.replaceAll("_", " ")}${d.date ? ` · ${d.date}` : ""} · ${d.page_ids.length} pages · ${state(d) === "both" ? "read by counsel and the engineer" : state(d) === "unread" ? "not read" : state(d) === "excluded" ? "excluded by the lead" : `read by ${state(d)}`}`} />
              ))}
            </div>
            <div className="legend-row">
              <span><i className="cov cov-both" /> both roles</span>
              <span><i className="cov cov-counsel" /> counsel</span>
              <span><i className="cov cov-engineer" /> engineer</span>
              <span><i className="cov cov-excluded" /> excluded</span>
              <span><i className="cov cov-unread" /> unread</span>
              <span style={{ color: "var(--muted)" }}>One square per document, in source PDF order. Hover for details.</span>
            </div>
          </div>
        </section>

        <section className="section">
          <h2>Context stays bounded</h2>
          <p>
            The lead&apos;s prompt ranged from {leadMin.toLocaleString()} to {leadMax.toLocaleString()} tokens across its {leadCalls.length} decisions while
            the team read {b.coverage.pages_read.toLocaleString()} pages. It is rebuilt each time from the document index, counts and the reports it has
            received (and, for the final brief, the verified claim statements), never from page text.
          </p>
          <div className="grid-3">
            <BarChart title="Lead's prompt per decision (tokens)" xFmt={clock} fmt={(v) => `${Math.round(v / 1000)}k`}
                      points={leadCalls.map((c) => ({ x: c.t, y: c.prompt_tokens, label: `${clock(c.t)} · ${c.purpose}: ${c.prompt_tokens.toLocaleString()} tokens` }))} />
            <BarChart title="Counsel's and engineer's prompt per decision (tokens)" xFmt={clock} fmt={(v) => `${Math.round(v / 1000)}k`}
                      points={roleCalls.map((c) => ({ x: c.t, y: c.prompt_tokens, label: `${clock(c.t)} · ${c.actor} ${c.purpose}: ${c.prompt_tokens.toLocaleString()} tokens` }))} />
            <LineChart title="Distinct pages read" xFmt={clock} points={pts.map((p) => ({ x: p.t, y: p.pages, label: `${clock(p.t)}: ${p.pages} pages` }))} />
          </div>
          <p style={{ fontSize: 12, color: "var(--muted)" }}>Counsel and the engineer see their own verified claims when they review, so their prompts grow with what they have found, not with what they have read. Readers see only their own batch and end.</p>
        </section>

        <section className="section">
          <h2>Refusals <span className="num" style={{ color: "var(--muted)", fontWeight: 400 }}>({refusals.length})</span></h2>
          <p>Claims the verifier would not accept, even after the one automatic repair, with its reasons. They never reach the chronology or the party map.</p>
          <div className="card table-wrap" style={{ maxHeight: 480, overflowY: "auto" }}>
            <table className="data">
              <thead><tr><th>Claim</th><th>Reason</th></tr></thead>
              <tbody>
                {refusals.map((r) => (
                  <tr key={r.id}>
                    <td><OpenEvidence className="row-open" claimIds={[r.id]} title={r.statement} eyebrow="Refused claim"><span className="row-title">{r.statement}</span></OpenEvidence></td>
                    <td style={{ color: "var(--muted)" }}>{r.reasons[0]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="section">
          <h2>Absences <span className="num" style={{ color: "var(--muted)", fontWeight: 400 }}>({b.negatives.length})</span></h2>
          <p>What the claim file does not contain, accepted only because every page in scope was read and a phrase search found no counter-example.</p>
          {b.negatives.length ? (
            <div className="card pad"><ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>{b.negatives.map((n) => <li key={n}>{n}</li>)}</ul></div>
          ) : (
            <div className="empty">No absences were accepted in this run.</div>
          )}
        </section>
      </div>
    </EvidenceHost>
  );
}
