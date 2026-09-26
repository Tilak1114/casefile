"use client";

import { useEffect, useRef } from "react";

import type { Claim, DocumentRow, Highlight, PageRef } from "@/lib/types";

export type Lookup = {
  pages: Record<string, PageRef>;
  docOfPage: Record<string, DocumentRow>;
};

const KIND_LABEL: Record<string, string> = {
  event: "Event",
  party: "Party",
  relationship: "Relationship",
  alias: "Alias",
  negative: "Absence",
};
const ROLE_LABEL: Record<string, string> = {
  parties_reviewer: "Parties reviewer",
  technical_reviewer: "Technical reviewer",
  baseline: "Baseline",
};

export function roleLabel(role: string): string {
  return ROLE_LABEL[role] ?? role;
}

export function StatusPill({ claim }: { claim: Claim }) {
  if (claim.verified) return <span className="pill ok">✓ Verified</span>;
  if (claim.reasons[0]?.startsWith("pending")) return <span className="pill pend">… Pending</span>;
  return <span className="pill bad">✕ Refused</span>;
}

export function PageImage({ page, highlight }: { page: PageRef | undefined; highlight: Highlight }) {
  if (!page?.image) {
    return <div className="empty">No image for {highlight.page_id}</div>;
  }
  return (
    <figure className="pageimg" style={{ margin: 0 }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={page.image} alt={`PDF ${page.file_no}, page ${page.page}`} loading="lazy" />
      {highlight.boxes.map((b, i) => (
        <span
          key={i}
          className="hl"
          style={{ left: `${b.left * 100}%`, top: `${b.top * 100}%`, width: `${b.width * 100}%`, height: `${b.height * 100}%` }}
        />
      ))}
      <figcaption>
        PDF {String(page.file_no).padStart(3, "0")} · page {page.page}
        {highlight.boxes.length === 0 ? " · location on page not available" : " · highlighted where the quote was read"}
      </figcaption>
    </figure>
  );
}

function DocumentMeta({ doc }: { doc: DocumentRow | undefined }) {
  if (!doc) return null;
  return (
    <dl className="kv">
      <dt>Document</dt>
      <dd>{doc.doc_type.replaceAll("_", " ")}{doc.date ? `, ${doc.date}` : ""}</dd>
      {doc.author && (<><dt>From</dt><dd>{doc.author}</dd></>)}
      {doc.recipient && (<><dt>To</dt><dd>{doc.recipient}</dd></>)}
      <dt>Source</dt>
      <dd className="mono">PDF {String(doc.file_no).padStart(3, "0")} · {doc.id.split(":").pop()}</dd>
    </dl>
  );
}

export function ClaimEvidence({ claim, lookup }: { claim: Claim; lookup: Lookup }) {
  const firstPage = claim.highlights[0]?.page_id;
  return (
    <div className="claim-block">
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <StatusPill claim={claim} />
        <span className="tag">{KIND_LABEL[claim.kind] ?? claim.kind}</span>
        <span className="tag">{roleLabel(claim.role)}</span>
        {claim.repair_of && <span className="tag">repaired</span>}
      </div>
      <p style={{ fontWeight: 600 }}>{claim.statement}</p>
      {firstPage && <DocumentMeta doc={lookup.docOfPage[firstPage]} />}
      {claim.highlights.map((h, i) => (
        <div key={i} style={{ display: "grid", gap: 8 }}>
          <blockquote className="quote">“{h.quote}”</blockquote>
          <PageImage page={lookup.pages[h.page_id]} highlight={h} />
        </div>
      ))}
      <ul className="checks" aria-label="Checks">
        {claim.verified
          ? claim.checks.map((c) => (<li key={c}><span className="yes" aria-hidden>✓</span>{c}</li>))
          : claim.reasons.map((r) => (<li key={r}><span className="no" aria-hidden>✕</span>{r}</li>))}
      </ul>
      <div className="mono" style={{ color: "var(--faint)", fontSize: 11 }}>claim {claim.id} · reader {claim.worker_id}</div>
    </div>
  );
}

export function EvidencePanel({
  title, eyebrow, claims, lookup, onClose,
}: { title: string; eyebrow?: string; claims: Claim[]; lookup: Lookup; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <aside className="panel" aria-label="Evidence">
      <div className="panel-head">
        <div style={{ display: "grid", gap: 4 }}>
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h2>{title}</h2>
        </div>
        <button ref={closeRef} className="panel-close" onClick={onClose}>Close</button>
      </div>
      <div className="panel-body">
        {claims.length === 0 ? <div className="empty">No claims for this item.</div> : claims.map((c) => <ClaimEvidence key={c.id} claim={c} lookup={lookup} />)}
      </div>
    </aside>
  );
}
