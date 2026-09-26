import type { Bundle } from "@/lib/types";

type Spec = Bundle["team_spec"];

function TeamDiagram() {
  const box = { fill: "var(--surface)", stroke: "var(--line-strong)", strokeWidth: 1.2 };
  const code = { fill: "var(--raised)", stroke: "var(--line-strong)", strokeWidth: 1.2, strokeDasharray: "4 3" };
  const hub = { fill: "var(--accent-soft)", stroke: "var(--accent)", strokeWidth: 2 };
  const t = { fill: "var(--ink)", fontSize: 13, fontWeight: 650, fontFamily: "var(--font-ui)", textAnchor: "middle" } as const;
  const s = { fill: "var(--muted)", fontSize: 11, fontFamily: "var(--font-ui)", textAnchor: "middle" } as const;
  const lbl = { fill: "var(--muted)", fontSize: 10.5, fontFamily: "var(--font-mono)" } as const;
  const line = { stroke: "var(--ink)", strokeWidth: 1.2, fill: "none", markerEnd: "url(#ah)" } as const;
  return (
    <figure className="card pad" style={{ margin: 0, overflowX: "auto" }}>
      <svg viewBox="0 0 1000 430" style={{ minWidth: 760, width: "100%", height: "auto" }} role="img"
           aria-label="The lead, counsel and the engineer never call each other. Each publishes events to the MongoDB event log; the dispatcher turns events into tasks for the roles that subscribe. Counsel and the engineer start readers; the verifier checks every claim before it is stored.">
        <defs>
          <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" fill="var(--ink)" />
          </marker>
        </defs>
        {/* lead */}
        <rect x={380} y={14} width={240} height={62} rx={4} {...box} />
        <text x={500} y={40} {...t}>Claim professional (lead)</text>
        <text x={500} y={58} {...s}>index and counts only · never page text</text>
        {/* roles */}
        <rect x={30} y={150} width={240} height={62} rx={4} {...box} />
        <text x={150} y={176} {...t}>Defense counsel</text>
        <text x={150} y={194} {...s}>parties, relationships, approvals</text>
        <rect x={730} y={150} width={240} height={62} rx={4} {...box} />
        <text x={850} y={176} {...t}>Forensic engineer</text>
        <text x={850} y={194} {...s}>starts only after the lead approves</text>
        {/* hub */}
        <rect x={380} y={140} width={240} height={82} rx={4} {...hub} />
        <text x={500} y={170} {...t} fill="var(--accent)">Event log · MongoDB</text>
        <text x={500} y={188} {...s}>append-only, ordered, with causes</text>
        <text x={500} y={204} {...s}>change streams wake consumers</text>
        {/* dispatcher */}
        <rect x={380} y={262} width={240} height={56} rx={4} {...code} />
        <text x={500} y={286} {...t}>Dispatcher (code)</text>
        <text x={500} y={303} {...s}>events → tasks · waits-for · deadlines · cap</text>
        {/* readers */}
        <rect x={30} y={262} width={240} height={56} rx={4} {...box} />
        <text x={150} y={286} {...t}>Counsel&apos;s readers</text>
        <text x={150} y={303} {...s}>whole documents · exact quotes</text>
        <rect x={730} y={262} width={240} height={56} rx={4} {...box} />
        <text x={850} y={286} {...t}>Engineer&apos;s readers</text>
        <text x={850} y={303} {...s}>whole documents · exact quotes</text>
        {/* verifier */}
        <rect x={30} y={360} width={940} height={52} rx={4} {...code} />
        <text x={500} y={382} {...t}>Verifier (code): every quote matched to its page before a claim counts</text>
        <text x={500} y={399} {...s}>findings · refusals · coverage · exclusions · model calls, all in MongoDB</text>

        {/* publish / wake */}
        <line x1={492} y1={76} x2={492} y2={138} {...line} />
        <line x1={508} y1={138} x2={508} y2={78} {...line} />
        <text x={430} y={112} {...lbl}>publishes</text>
        <text x={516} y={112} {...lbl}>wakes</text>
        <line x1={270} y1={174} x2={378} y2={174} {...line} />
        <line x1={378} y1={190} x2={272} y2={190} {...line} />
        <text x={286} y={168} {...lbl}>publishes</text>
        <text x={300} y={205} {...lbl}>wakes</text>
        <line x1={730} y1={174} x2={622} y2={174} {...line} />
        <line x1={622} y1={190} x2={728} y2={190} {...line} />
        <text x={660} y={168} {...lbl}>publishes</text>
        <text x={672} y={205} {...lbl}>wakes</text>
        <line x1={500} y1={222} x2={500} y2={260} {...line} />
        <text x={508} y={246} {...lbl}>turns events into tasks</text>
        <line x1={150} y1={212} x2={150} y2={260} {...line} />
        <text x={158} y={240} {...lbl}>starts</text>
        <line x1={850} y1={212} x2={850} y2={260} {...line} />
        <text x={858} y={240} {...lbl}>starts</text>
        <line x1={150} y1={318} x2={150} y2={358} {...line} />
        <line x1={850} y1={318} x2={850} y2={358} {...line} />
        <text x={158} y={342} {...lbl}>every claim</text>
        <text x={858} y={342} {...lbl}>every claim</text>
      </svg>
      <figcaption style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>
        No agent calls another. Each publishes typed events, which the dispatcher turns into tasks for the roles that subscribe to them. Solid boxes use the model; dashed boxes are code.
      </figcaption>
    </figure>
  );
}

function Tags({ items }: { items: string[] }) {
  if (!items.length) return <span style={{ color: "var(--faint)" }}>—</span>;
  return <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 4 }}>{items.map((i) => <span key={i} className="tag">{i}</span>)}</span>;
}

export function HarnessTeam({ spec, runId }: { spec: Spec; runId: string }) {
  return (
    <div className="page">
      <div className="page-head">
        <div className="eyebrow">How it works · read from the code</div>
        <h1>The harness: a claims team</h1>
        <p>
          The team mirrors how a liability claim is worked: the claim professional owns the file, defense counsel works out the
          parties, and a forensic engineer (retained with the claim professional&apos;s approval) works out the technical record.
          They read through readers, collaborate through events, and nothing a model writes counts until the verifier has checked it
          against the page. Run {runId}&apos;s own trajectory is on the <a href="/trajectory">Trajectory</a> screen.
        </p>
      </div>

      <section className="section">
        <h2>How the pieces talk</h2>
        <TeamDiagram />
      </section>

      <section className="section">
        <h2>Who does what</h2>
        <div className="grid-2">
          {spec.members.map((m) => (
            <div key={m.actor} className="card pad" style={{ display: "grid", gap: 8, alignContent: "start", borderStyle: m.kind === "code" ? "dashed" : "solid" }}>
              <div className="eyebrow">{m.kind === "code" ? "Code · deterministic" : "Agent · model"} · mirrors {m.mirrors}</div>
              <strong style={{ fontSize: 15 }}>{m.title}</strong>
              <div style={{ fontSize: 13 }}>{m.job}</div>
              <dl className="kv">
                <dt>Sees</dt><dd>{m.sees}</dd>
                <dt>Can</dt><dd><ul style={{ margin: 0, paddingLeft: 16 }}>{m.can.map((c) => <li key={c}>{c}</li>)}</ul></dd>
                <dt>Never</dt><dd>{m.never}</dd>
                <dt>Waits for</dt><dd>{m.waits_for}</dd>
                <dt>Wakes on</dt><dd><Tags items={m.wakes_on} /></dd>
                <dt>Publishes</dt><dd><Tags items={m.publishes} /></dd>
              </dl>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <h2>The event catalogue</h2>
        <p>The dispatcher refuses any event its sender is not allowed to publish, and wakes only the roles subscribed to it.</p>
        <div className="card table-wrap">
          <table className="data">
            <thead><tr><th>Event</th><th>Published by</th><th>Wakes</th></tr></thead>
            <tbody>
              {spec.events.map((e) => (
                <tr key={e.type}><td className="mono">{e.type}</td><td><Tags items={e.published_by} /></td><td><Tags items={e.wakes} /></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <h2>Verifier rules</h2>
        <div className="card pad">
          <ul className="checks">{spec.verifier_rules.map((r) => <li key={r}><span className="yes" aria-hidden>✓</span>{r}</li>)}</ul>
        </div>
        <div className="card pad" style={{ fontSize: 13 }}><strong>Absences.</strong> {spec.negative_rule}</div>
      </section>

      <div className="grid-2">
        <section className="section">
          <h2>Guards</h2>
          <div className="card table-wrap">
            <table className="data"><tbody>
              {Object.entries(spec.guards).map(([k, v]) => (<tr key={k}><td>{k}</td><td className="num" style={{ textAlign: "right" }}>{v.toLocaleString()}</td></tr>))}
            </tbody></table>
          </div>
          <p style={{ fontSize: 12, color: "var(--muted)" }}>The lead may close the claim file only when code confirms every document is read or excluded, no task is open and no dispute is open.</p>
        </section>
        <section className="section">
          <h2>Memory in MongoDB</h2>
          <div className="card table-wrap">
            <table className="data"><tbody>
              {Object.entries(spec.memory).map(([k, v]) => (<tr key={k}><td className="mono" style={{ whiteSpace: "nowrap" }}>{k}</td><td>{v}</td></tr>))}
            </tbody></table>
          </div>
        </section>
      </div>
    </div>
  );
}
