"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Board" },
  { href: "/chronology", label: "Chronology" },
  { href: "/parties", label: "Parties" },
  { href: "/harness", label: "Harness" },
  { href: "/memory", label: "Memory" },
  { href: "/evaluation", label: "Evaluation" },
];

export function Rail() {
  const path = usePathname();
  return (
    <nav className="rail" aria-label="Screens">
      {LINKS.map((l) => (
        <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined}>
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
