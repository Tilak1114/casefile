import { EvidenceHost, OpenEvidence } from "@/components/EvidenceHost";
import { claimsById, loadBundle, lookupFor, partyName } from "@/lib/data";

const TYPE_LABEL: Record<string, string> = {
  contracted_with: "contracted with", designed_for: "designed for", represented: "represented",
  reviewed_submittals_for: "reviewed submittals for", supplied: "supplied", subcontracted_to: "subcontracted to",
  inspected_for: "inspected for", oversaw: "oversaw",
};

export default function PartiesPage() {
  const b = loadBundle();
  const claims = claimsById(b);
  const used = [...b.parties.flatMap((p) => p.claim_ids), ...b.links.flatMap((l) => l.claim_ids)].map((id) => claims[id]).filter(Boolean);
  const aliases = b.claims.filter((c) => c.kind === "alias");
  const parties = [...b.parties].sort((a, z) => z.claim_ids.length - a.claim_ids.length);
  return (
    <EvidenceHost claims={Object.fromEntries([...used, ...aliases].map((c) => [c.id, c]))} lookup={lookupFor(b, [...used, ...aliases])}>
      <div className="page">
        <div className="page-head">
          <div className="eyebrow">Deliverable · party map</div>
          <h1>Parties</h1>
          <p>Who appears in the record and how they are related. Names are merged only when they differ in formatting (case, punctuation, “Inc.”) or when a quote shows both names. Every link cites its source.</p>
        </div>
        <section className="section">
          <h2>Relationships <span className="num" style={{ color: "var(--muted)", fontWeight: 400 }}>({b.links.length})</span></h2>
          <div className="card table-wrap">
            <table className="data">
              <thead><tr><th>Party</th><th>Relationship</th><th>Party</th><th>Evidence</th></tr></thead>
              <tbody>
                {b.links.map((l, i) => (
                  <tr key={i}>
                    <td>{partyName(b, l.source)}</td>
                    <td><span className="tag">{TYPE_LABEL[l.type] ?? l.type}</span></td>
                    <td>{partyName(b, l.target)}</td>
                    <td><OpenEvidence claimIds={l.claim_ids} title={`${partyName(b, l.source)} ${TYPE_LABEL[l.type] ?? l.type} ${partyName(b, l.target)}`} eyebrow="Relationship">{l.claim_ids.length} quote{l.claim_ids.length > 1 ? "s" : ""}</OpenEvidence></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="section">
          <h2>Parties <span className="num" style={{ color: "var(--muted)", fontWeight: 400 }}>({parties.length})</span></h2>
          <div className="grid-3">
            {parties.map((p) => (
              <div key={p.id} className="card pad" style={{ display: "grid", gap: 6, alignContent: "start" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <strong>{partyName(b, p.id)}</strong>
                  <span className="tag">{p.kind}</span>
                </div>
                {p.names.length > 1 && <div style={{ fontSize: 12, color: "var(--muted)" }}>Also written: {p.names.filter((n) => n !== partyName(b, p.id)).join(" · ")}</div>}
                <div style={{ fontSize: 13 }}>{p.roles.slice(0, 3).join("; ")}</div>
                <OpenEvidence claimIds={p.claim_ids} title={partyName(b, p.id)} eyebrow="Party">{p.claim_ids.length} quote{p.claim_ids.length > 1 ? "s" : ""}</OpenEvidence>
              </div>
            ))}
          </div>
        </section>
      </div>
    </EvidenceHost>
  );
}
