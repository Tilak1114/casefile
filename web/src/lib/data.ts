import { readFileSync } from "node:fs";
import path from "node:path";

import type { Bundle, Claim, DocumentRow } from "./types";

// The run shown in the UI. Exported by `casefile export RUN_ID`.
export const RUN_ID = process.env.CASEFILE_RUN ?? "full-1";

let cached: Bundle | null = null;

/** Read at build time (server components only). */
export function loadBundle(): Bundle {
  if (!cached) {
    const file = path.join(process.cwd(), "public", "data", "runs", `${RUN_ID}.json`);
    cached = JSON.parse(readFileSync(file, "utf8")) as Bundle;
  }
  return cached;
}

export function documentOfPage(bundle: Bundle): Record<string, DocumentRow> {
  const out: Record<string, DocumentRow> = {};
  for (const d of bundle.documents) for (const p of d.page_ids) out[p] = d;
  return out;
}

export function claimsById(bundle: Bundle): Record<string, Claim> {
  const out: Record<string, Claim> = {};
  for (const c of [...bundle.claims, ...bundle.refusals]) out[c.id] = c;
  return out;
}

export function pageLabel(pageId: string): string {
  const [, file, page] = pageId.split(":");
  return `PDF ${file} · p.${Number(page.slice(1))}`;
}

import type { PageRef } from "./types";
import type { Lookup } from "@/components/Evidence";

/** Page images and documents for every page cited by the given claims, for the evidence panel. */
export function lookupFor(bundle: Bundle, claims: Claim[]): Lookup {
  const docOf = documentOfPage(bundle);
  const pages: Record<string, PageRef> = {};
  const docOfPage: Record<string, DocumentRow> = {};
  for (const c of claims) for (const h of c.highlights) {
    if (bundle.pages[h.page_id]) pages[h.page_id] = bundle.pages[h.page_id];
    if (docOf[h.page_id]) docOfPage[h.page_id] = docOf[h.page_id];
  }
  return { pages, docOfPage };
}

export function partyName(bundle: Bundle, id: string): string {
  const p = bundle.parties.find((x) => x.id === id);
  return p ? p.names.reduce((a, b) => (b.length > a.length ? b : a), p.names[0]) : id;
}
