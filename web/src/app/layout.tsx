import type { Metadata } from "next";
import { IBM_Plex_Mono, Public_Sans, Source_Serif_4 } from "next/font/google";

import { Rail } from "@/components/Rail";
import { loadBundle } from "@/lib/data";

import "@xyflow/react/dist/style.css";
import "./globals.css";

const publicSans = Public_Sans({ subsets: ["latin"], variable: "--font-public-sans", weight: ["400", "500", "600", "700"] });
const sourceSerif = Source_Serif_4({ subsets: ["latin"], variable: "--font-source-serif", style: ["normal", "italic"] });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-plex-mono", weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "Casefile",
  description: "A cited reconstruction of a construction project's record, built by an agent harness.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const b = loadBundle();
  const refused = b.refusals.filter((r) => r.kind !== "negative").length;
  return (
    <html lang="en" className={`${publicSans.variable} ${sourceSerif.variable} ${plexMono.variable}`}>
      <body>
        <div className="shell">
          <header className="bar">
            <div className="brand">Casefile</div>
            <div className="bar-case">
              <b>{b.case.case_id}</b>
              <span>{b.case.title}</span>
            </div>
            <div className="bar-metrics">
              <div className="metric"><em>Run</em>{b.run.run_id}</div>
              <div className="metric"><em>Pages read</em>{b.coverage.pages_read.toLocaleString()} / {b.coverage.pages_total.toLocaleString()}</div>
              <div className="metric"><em>Verified</em>{b.claims.length.toLocaleString()}</div>
              <div className="metric"><em>Refused</em>{refused}</div>
            </div>
          </header>
          <div className="notice" role="note">
            <span><strong>Real public record:</strong> NTSB docket {b.case.case_id}, {b.case.inputs} files read, {b.case.withheld.length} NTSB analysis files withheld.</span>
            <span><strong>Casefile quotes documents and never assigns fault.</strong></span>
            <span><strong>This run:</strong> {b.run.status}.</span>
          </div>
          <Rail />
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
