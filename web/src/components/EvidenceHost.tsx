"use client";

import { createContext, useCallback, useContext, useState } from "react";

import type { Claim } from "@/lib/types";

import { EvidencePanel, type Lookup } from "./Evidence";

type OpenArgs = { claimIds: string[]; title: string; eyebrow?: string };
const Ctx = createContext<(args: OpenArgs) => void>(() => {});

export function EvidenceHost({
  claims, lookup, children,
}: { claims: Record<string, Claim>; lookup: Lookup; children: React.ReactNode }) {
  const [open, setOpen] = useState<OpenArgs | null>(null);
  const close = useCallback(() => setOpen(null), []);
  return (
    <Ctx.Provider value={setOpen}>
      {children}
      {open && (
        <EvidencePanel
          title={open.title}
          eyebrow={open.eyebrow}
          claims={open.claimIds.map((id) => claims[id]).filter(Boolean)}
          lookup={lookup}
          onClose={close}
        />
      )}
    </Ctx.Provider>
  );
}

/** A button that opens the evidence panel for the given claims. */
export function OpenEvidence({
  claimIds, title, eyebrow, children, className,
}: OpenArgs & { children: React.ReactNode; className?: string }) {
  const open = useContext(Ctx);
  return (
    <button type="button" className={className ?? "link-button"} onClick={() => open({ claimIds, title, eyebrow })}>
      {children}
    </button>
  );
}
