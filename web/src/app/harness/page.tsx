import { HarnessTeam } from "@/components/HarnessTeam";
import { loadBundle } from "@/lib/data";
import type { TraceRow } from "@/lib/types";

function LoopDiagram() {
  const box = { fill: "var(--surface)", stroke: "var(--line-strong)", strokeWidth: 1.2 };
  const t = { fill: "var(--ink)", fontSize: 13, fontWeight: 600, fontFamily: "var(--font-ui)" } as const;
  const s = { fill: "var(--muted)", fontSize: 11, fontFamily: "var(--font-ui)" } as const;
  const steps: [string, string][] = [
    ["Load state", "from MongoDB"], ["Examiner decides", "one typed action"], ["Validate", "schema and guards"],
    ["Roles act", "start readers"], ["Verify", "every claim"], ["Record", "findings, coverage, trace"],
  ];
  return (
    <figure className="card pad" style={{ margin: 0, overflowX: "auto" }}>
      <svg viewBox="0 0 1000 250" style={{ minWidth: 760, width: "100%", height: "auto" }} role="img"
           aria-label="Each turn loads state from MongoDB, the examiner decides one action, it is validated, roles act by starting readers, every claim is verified, results are recorded, then the run checkpoints and starts the next turn.">
        <defs>
          <marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" fill="var(--ink)" />
          </marker>
        </defs>
        {steps.map(([a, b], i) => {
          const x = 20 + i * 165;
          const verify = i === 4;
          return (
            <g key={a}>
              <rect x={x} y={40} width={140} height={70} rx={4} {...box} {...(verify ? { stroke: "var(--accent)", strokeWidth: 2, fill: "var(--accent-soft)" } : {})} />
              <text x={x + 70} y={70} textAnchor="middle" {...t} {...(verify ? { fill: "var(--accent)" } : {})}>{a}</text>
              <text x={x + 70} y={90} textAnchor="middle" {...s}>{b}</text>
              {i < 5 && <line x1={x + 140} y1={75} x2={x + 163} y2={75} stroke="var(--ink)" strokeWidth={1.2} markerEnd="url(#ar)" />}
            </g>
          );
        })}
        <polyline points="915,110 915,170 90,170 90,112" fill="none" stroke="var(--ink)" strokeWidth={1.2} markerEnd="url(#ar)" />
        <text x={500} y={192} textAnchor="middle" {...s}>checkpoint, then the next turn, until every document is read or a guard stops the run</text>
        <polyline points="420,110 420,140 255,140 255,112" fill="none" stroke="var(--ink)" strokeWidth={1.2} strokeDasharray="4 3" markerEnd="url(#ar)" />
        <text x={338} y={156} textAnchor="middle" {...s}>invalid action: refused with the reason</text>
        <text x={500} y={232} textAnchor="middle" {...s}>After the loop: each role proposes absences (checked against coverage and search), then the party map, chronology, exhibits and coverage report are assembled by code.</text>
      </svg>
    </figure>
  );
}

type Turn = { turn: number; decision?: TraceRow; rejected?: TraceRow; worker?: TraceRow; progress?: TraceRow };

export default function HarnessPage() {
  const b = loadBundle();
  if (b.team) return <HarnessTeam spec={b.team_spec} runId={b.run.run_id} />;
  const h = b.harness;
  const turns: Turn[] = [];
  for (const t of b.trace) {
    if (!["decision", "rejected", "worker", "progress"].includes(t.kind)) continue;
    let row = turns.find((x) => x.turn === t.turn);
    if (!row) { row = { turn: t.turn }; turns.push(row); }
    (row as Record<string, unknown>)[t.kind] = t;
  }
  const actionCounts = turns.reduce<Record<string, number>>((acc, t) => {
    const a = (t.decision?.action as { action?: string } | null)?.action;
    if (a) acc[a] = (acc[a] ?? 0) + 1;
    return acc;
  }, {});
  return (
    <div className="page">
      <div className="page-head">
        <div className="eyebrow">How it works · read from the code</div>
        <h1>The harness</h1>
        <p>A claims examiner leads the investigation and assigns work to two reviewer roles, which start readers on whole documents. Nothing a model writes counts until the verifier has checked it against the page. The state lives in MongoDB, so the examiner&apos;s prompt stays the same size however long the run is.</p>
      </div>

      <section className="section">
        <h2>One turn</h2>
        <LoopDiagram />
      </section>

      <section className="section">
        <h2>Who does what</h2>
        <div className="grid-3">
          <div className="card pad" style={{ display: "grid", gap: 8, alignContent: "start" }}>
            <div className="eyebrow">Lead · model</div>
            <strong>Claims examiner</strong>
            <div style={{ fontSize: 13 }}>Mirrors the claims professional who owns the claim and relies on experts.</div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>Sees</div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>{h.examiner_sees.map((x) => <li key={x}>{x}</li>)}</ul>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>Can</div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>{h.examiner_actions.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
          {h.roles.map((r) => (
            <div key={r.role} className="card pad" style={{ display: "grid", gap: 8, alignContent: "start" }}>
              <div className="eyebrow">Role · model</div>
              <strong>{r.title}</strong>
              <div style={{ fontSize: 13 }}>Mirrors {r.mirrors}.</div>
              <div style={{ fontSize: 13, color: "var(--muted)" }}>{r.brief}</div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>Default focus</div>
              <div style={{ fontSize: 13 }}>{r.default_focus}</div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>Sees · tools</div>
              <div style={{ fontSize: 13 }}>{r.sees} · {r.tools.join(", ")}</div>
            </div>
          ))}
          <div className="card pad" style={{ display: "grid", gap: 8, alignContent: "start" }}>
            <div className="eyebrow">Worker · model, on the go</div>
            <strong>Readers</strong>
            <div style={{ fontSize: 13 }}>Started by a role on a batch of whole documents (about {h.guards["pages per reader"]} pages), at most {h.guards["readers at once"]} at once. Each returns dated events, parties, relationships, aliases and open questions, every one quoted.</div>
            <div style={{ fontSize: 13 }}>The harness, not the model, records which pages a reader was given, before the model runs.</div>
          </div>
          <div className="card pad" style={{ display: "grid", gap: 8, alignContent: "start" }}>
            <div className="eyebrow">Code · deterministic</div>
            <strong>Verifier, assembly, negatives</strong>
            <div style={{ fontSize: 13 }}>No model involved. Checks every claim, assembles the party map, chronology, exhibits and coverage report, and tests every proposed absence.</div>
          </div>
        </div>
      </section>

      <section className="section">
        <h2>Verifier rules</h2>
        <div className="card pad">
          <ul className="checks">{h.verifier_rules.map((r) => <li key={r}><span className="yes" aria-hidden>✓</span>{r}</li>)}</ul>
        </div>
        <div className="card pad" style={{ fontSize: 13 }}><strong>Absences.</strong> {h.negative_rule}</div>
      </section>

      <div className="grid-2">
        <section className="section">
          <h2>Guards</h2>
          <div className="card table-wrap">
            <table className="data"><tbody>
              {Object.entries(h.guards).map(([k, v]) => (<tr key={k}><td>{k}</td><td className="num" style={{ textAlign: "right" }}>{v.toLocaleString()}</td></tr>))}
            </tbody></table>
          </div>
        </section>
        <section className="section">
          <h2>Memory in MongoDB</h2>
          <div className="card table-wrap">
            <table className="data"><tbody>
              {Object.entries(h.memory_collections).map(([k, v]) => (<tr key={k}><td className="mono" style={{ whiteSpace: "nowrap" }}>{k}</td><td>{v}</td></tr>))}
            </tbody></table>
          </div>
        </section>
      </div>

      {!b.team && <section className="section">
        <h2>Run {b.run.run_id}, turn by turn</h2>
        <p>{b.run.status}. Actions: {Object.entries(actionCounts).map(([k, v]) => `${v} ${k}`).join(", ")}.</p>
        <div className="card pad" style={{ display: "grid", gap: 6, fontSize: 13, borderColor: "var(--pend)" }}>
          <strong>Observed in this run, for review</strong>
          <span>The examiner alternated between assigning a few documents and spending a whole turn on repairs, so coverage grew slowly (see the Memory screen).</span>
          <span>The run stopped at turn {b.run.turns - 1} when the Atlas cluster briefly had no primary; the database client now waits 30 s instead of 5 s. The run is checkpointed and can resume.</span>
          <span>No absences were proposed: that step runs after the loop, which was not reached.</span>
        </div>
        <div className="card table-wrap">
          <table className="data">
            <thead><tr><th>Turn</th><th>Action</th><th>Examiner&apos;s reason</th><th>Result</th><th>Pages read</th><th>Verified</th><th>Refused</th><th>Context</th></tr></thead>
            <tbody>
              {turns.map((t) => {
                const a = (t.decision?.action as { action?: string } | null)?.action;
                return (
                  <tr key={t.turn}>
                    <td className="num">{t.turn + 1}</td>
                    <td>{t.rejected ? <span className="pill bad">rejected</span> : a ? <span className={`pill ${a === "repair" ? "pend" : "accent"}`}>{a}</span> : "—"}</td>
                    <td style={{ maxWidth: 420 }}>{t.rejected?.summary ?? t.decision?.summary}</td>
                    <td style={{ maxWidth: 260, color: "var(--muted)" }}>{t.worker?.summary ?? "—"}</td>
                    <td className="num">{t.progress?.coverage_pages ?? "—"}</td>
                    <td className="num">{t.progress?.verified_total ?? "—"}</td>
                    <td className="num">{t.progress?.refused_total ?? "—"}</td>
                    <td className="num">{t.decision?.context_chars ? `${Math.round(t.decision.context_chars / 1000)}k chars` : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>}
    </div>
  );
}
