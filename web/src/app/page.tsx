import { Board } from "@/components/Board";
import type { Claim, PageRef } from "@/lib/types";
import { claimsById, documentOfPage, loadBundle } from "@/lib/data";

export default function BoardPage() {
  const b = loadBundle();
  const claims = claimsById(b);
  const needed = new Set<string>();
  const used: Record<string, Claim> = {};
  for (const r of b.chronology) for (const id of r.claim_ids) {
    const c = claims[id];
    if (c) { used[id] = c; c.highlights.forEach((h) => needed.add(h.page_id)); }
  }
  const pages: Record<string, PageRef> = {};
  needed.forEach((p) => { if (b.pages[p]) pages[p] = b.pages[p]; });
  const docOf = documentOfPage(b);
  const docOfPage = Object.fromEntries([...needed].filter((p) => docOf[p]).map((p) => [p, docOf[p]]));
  const core = b.answer_key.filter((k) => k.core).flatMap((k) => k.found_by);
  const any = b.answer_key.flatMap((k) => k.found_by);
  return <Board rows={b.chronology} lanes={b.lanes} claims={used} lookup={{ pages, docOfPage }} keyClaims={{ any, core }} />;
}
