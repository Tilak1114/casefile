import { EvidenceHost, OpenEvidence } from "@/components/EvidenceHost";
import { claimsById, documentOfPage, loadBundle, lookupFor } from "@/lib/data";

export default function ChronologyPage() {
  const b = loadBundle();
  const claims = claimsById(b);
  const used = b.chronology.flatMap((r) => r.claim_ids.map((id) => claims[id]).filter(Boolean));
  const lane = Object.fromEntries(b.lanes.map((l) => [l.id, l.label]));
  const docOf = documentOfPage(b);
  const docs = Object.fromEntries(b.documents.map((d) => [d.id, d]));
  return (
    <EvidenceHost claims={Object.fromEntries(used.map((c) => [c.id, c]))} lookup={lookupFor(b, used)}>
      <div className="page">
        <div className="page-head">
          <div className="eyebrow">Deliverable · chronology</div>
          <h1>Chronology</h1>
          <p>Every verified event, in date order. Events two reviewers found on the same page and date are merged. Open a row to see the quote on its page.</p>
        </div>
        <div className="card table-wrap">
          <table className="data">
            <thead><tr><th>Date</th><th>Event</th><th>Party</th><th>Document</th><th>Found by</th></tr></thead>
            <tbody>
              {b.chronology.map((r) => {
                const d = r.document_id ? docs[r.document_id] : undefined;
                const first = claims[r.claim_ids[0]];
                const page = first?.highlights[0]?.page_id;
                return (
                  <tr key={r.claim_ids[0]}>
                    <td className="date">{r.date}</td>
                    <td>
                      <OpenEvidence className="row-open" claimIds={r.claim_ids} title={r.statement} eyebrow={`Event · ${r.date}`}>
                        <span className="row-title">{r.statement}</span>
                      </OpenEvidence>
                    </td>
                    <td>{lane[r.lane] ?? "Other parties"}</td>
                    <td>{d ? `${d.doc_type.replaceAll("_", " ")}${page ? ` · ${page.split(":").slice(1).join(" ")}` : ""}` : (page && docOf[page]?.doc_type) || "—"}</td>
                    <td>{r.roles.map((x) => (x.startsWith("parties") ? "Parties" : "Technical")).join(", ")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </EvidenceHost>
  );
}
