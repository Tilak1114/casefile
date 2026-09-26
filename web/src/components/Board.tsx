"use client";

import { Controls, MiniMap, ReactFlow, type Node, type NodeProps, type Viewport } from "@xyflow/react";
import { useCallback, useMemo, useState } from "react";

import type { ChronologyRow, Claim, Lane } from "@/lib/types";

import { EvidencePanel, type Lookup } from "./Evidence";

const PX_PER_DAY = 6;
const CARD_W = 176;
const CARD_H = 74;
const ROW_GAP = 10;
const LANE_PAD = 14;
const MAX_ROWS = 3; // cards stacked per lane; more fold into a "+N more" badge
const AXIS_H = 34;
const START = Date.UTC(1997, 0, 1);
const END = Date.UTC(2007, 11, 31);

function dayX(date: string): number {
  const [y, m = "06", d = "15"] = date.split("-");
  return ((Date.UTC(Number(y), Number(m) - 1, Number(d)) - START) / 86_400_000) * PX_PER_DAY;
}

type EventData = { row: ChronologyRow; more: ChronologyRow[]; inKey: boolean; core: boolean };
type LaneData = { width: number; height: number; shade: boolean };
type TickData = { label: string; height: number };

function EventCard({ data, selected }: NodeProps<Node<EventData>>) {
  const { row, core, inKey, more } = data;
  return (
    <div className={`ev${selected ? " sel" : ""}`}>
      <div className="ev-top">
        <span className="ev-date">{row.date}</span>
        <span className="ev-roles">{row.roles.map((r) => (r.startsWith("parties") ? "P" : "T")).join(" ")}</span>
      </div>
      <div className="ev-title">{row.statement}</div>
      <div className="ev-foot">
        <span className="ev-ok" aria-label="verified">✓</span>
        <span>{row.claim_ids.length > 1 ? `${row.claim_ids.length} claims` : "1 claim"}</span>
        {more.length > 0 && <span className="ev-more">+{more.length} more</span>}
        {inKey && <span className={`ev-key${core ? " core" : ""}`} title={core ? "Matches an answer-key event on the causal chain" : "Matches an answer-key event"}>{core ? "chain" : "key"}</span>}
      </div>
    </div>
  );
}

function LaneBand({ data }: NodeProps<Node<LaneData>>) {
  return <div className={`lane-band${data.shade ? " shade" : ""}`} style={{ width: data.width, height: data.height }} />;
}

function Tick({ data }: NodeProps<Node<TickData>>) {
  return (
    <div className="tick" style={{ height: data.height }}>
      <span>{data.label}</span>
    </div>
  );
}

const nodeTypes = { event: EventCard, lane: LaneBand, tick: Tick };

export function Board({
  rows, lanes, claims, lookup, keyClaims,
}: {
  rows: ChronologyRow[];
  lanes: Lane[];
  claims: Record<string, Claim>;
  lookup: Lookup;
  keyClaims: { any: string[]; core: string[] };
}) {
  const [role, setRole] = useState<"all" | "parties" | "technical">("all");
  const [onlyKey, setOnlyKey] = useState(false);
  const [open, setOpen] = useState<ChronologyRow | null>(null);
  const [vp, setVp] = useState<Viewport>({ x: 0, y: 0, zoom: 1 });

  const anyKey = useMemo(() => new Set(keyClaims.any), [keyClaims.any]);
  const coreKey = useMemo(() => new Set(keyClaims.core), [keyClaims.core]);

  const layout = useMemo(() => {
    const visible = rows.filter((r) => {
      if (role !== "all" && !r.roles.some((x) => x.startsWith(role))) return false;
      if (onlyKey && !r.claim_ids.some((c) => anyKey.has(c))) return false;
      return true;
    });
    const width = dayX("2007-12-31") + CARD_W;
    const laneTops: { lane: Lane; top: number; height: number }[] = [];
    const nodes: Node[] = [];
    let top = AXIS_H;
    // Lanes ordered by each party's median event date, so parties active on the project sit above
    // those who arrived later; "Other parties" last.
    const median = (id: string) => {
      const ds = rows.filter((r) => r.lane === id).map((r) => r.date).sort();
      return ds[Math.floor(ds.length / 2)] ?? "9999";
    };
    const ordered = [...lanes].sort((a, z) => (a.id === "other" ? 1 : z.id === "other" ? -1 : median(a.id).localeCompare(median(z.id))));
    ordered.forEach((lane, i) => {
      const inLane = visible.filter((r) => r.lane === lane.id).sort((a, b) => a.date.localeCompare(b.date));
      const rowEnds: number[] = [];
      const placed: { r: ChronologyRow; x: number; k: number; more: ChronologyRow[] }[] = [];
      const lastInRow: ({ more: ChronologyRow[] } | undefined)[] = [];
      for (const r of inLane) {
        const x = dayX(r.date);
        let k = rowEnds.findIndex((end) => end + 8 <= x);
        if (k === -1 && rowEnds.length < MAX_ROWS) { k = rowEnds.length; rowEnds.push(0); }
        if (k === -1) {
          // Lane is full here: fold into the card that ends first, shown as "+N more".
          const soonest = rowEnds.indexOf(Math.min(...rowEnds));
          lastInRow[soonest]?.more.push(r);
          continue;
        }
        rowEnds[k] = x + CARD_W;
        const card = { r, x, k, more: [] as ChronologyRow[] };
        placed.push(card);
        lastInRow[k] = card;
      }
      const height = Math.max(1, rowEnds.length) * (CARD_H + ROW_GAP) + LANE_PAD * 2;
      laneTops.push({ lane, top, height });
      nodes.push({ id: `lane-${lane.id}`, type: "lane", position: { x: 0, y: top }, data: { width, height, shade: i % 2 === 0 },
                   draggable: false, selectable: false, focusable: false, zIndex: -2 });
      for (const { r, x, k, more } of placed) {
        nodes.push({
          id: r.claim_ids[0], type: "event", position: { x, y: top + LANE_PAD + k * (CARD_H + ROW_GAP) },
          data: { row: r, more, inKey: [r, ...more].some((x) => x.claim_ids.some((c) => anyKey.has(c))), core: [r, ...more].some((x) => x.claim_ids.some((c) => coreKey.has(c))) },
          draggable: false,
        });
      }
      top += height;
    });
    for (let y = 1997; y <= 2007; y++) {
      nodes.push({ id: `tick-${y}`, type: "tick", position: { x: dayX(`${y}-01-01`), y: 0 }, data: { label: String(y), height: top },
                   draggable: false, selectable: false, focusable: false, zIndex: -1 });
    }
    return { nodes, laneTops, count: visible.length };
  }, [rows, lanes, role, onlyKey, anyKey, coreKey]);

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    if (node.type === "event") {
      const d = node.data as EventData;
      setOpen({ ...d.row, claim_ids: [d.row, ...d.more].flatMap((x) => x.claim_ids),
                statement: d.more.length ? `${d.row.statement} (and ${d.more.length} more on or near ${d.row.date})` : d.row.statement });
    }
  }, []);

  // Open at the densest quarter of the record, at the top, at a zoom where cards are readable.
  const initial = useMemo(() => {
    const byQuarter = new Map<string, number>();
    for (const r of rows) {
      const q = `${r.date.slice(0, 4)}-${Math.floor((Number(r.date.slice(5, 7) || "6") - 1) / 3)}`;
      byQuarter.set(q, (byQuarter.get(q) ?? 0) + 1);
    }
    const [best] = [...byQuarter.entries()].sort((a, z) => z[1] - a[1])[0] ?? ["1999-3", 0];
    const [y, q] = best.split("-").map(Number);
    return { x: -dayX(`${y}-${String(q * 3 + 1).padStart(2, "0")}-01`) * 0.85 + 190, y: 0, zoom: 0.85 };
  }, [rows]);

  return (
    <div className="board">
      <div className="board-bar">
        <div className="seg" role="group" aria-label="Role">
          {(["all", "parties", "technical"] as const).map((r) => (
            <button key={r} aria-pressed={role === r} onClick={() => setRole(r)}>
              {r === "all" ? "All roles" : r === "parties" ? "Parties reviewer" : "Technical reviewer"}
            </button>
          ))}
        </div>
        <button className="seg-single" aria-pressed={onlyKey} onClick={() => setOnlyKey((v) => !v)}>In the answer key</button>
        <span className="board-count num">{layout.count} events · drag to pan, scroll to zoom</span>
      </div>
      <div className="board-canvas">
        <div className="lane-labels" aria-hidden>
          {layout.laneTops.map(({ lane, top, height }) => (
            <div key={lane.id} className="lane-label"
                 style={{ top: top * vp.zoom + vp.y, height: height * vp.zoom }}>
              <span>{lane.label}</span><em className="num">{lane.events}</em>
            </div>
          ))}
        </div>
        <ReactFlow
          nodes={layout.nodes}
          edges={[]}
          nodeTypes={nodeTypes}
          defaultViewport={initial}
          onMove={(_, v) => setVp(v)}
          onInit={(inst) => setVp(inst.getViewport())}
          onNodeClick={onNodeClick}
          minZoom={0.15}
          maxZoom={1.6}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <MiniMap pannable zoomable nodeClassName={(n) => (n.type === "event" ? "mm-event" : "mm-none")} nodeStrokeWidth={0} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      {open && (
        <EvidencePanel
          eyebrow={`Event · ${open.date}`}
          title={open.statement}
          claims={open.claim_ids.map((id) => claims[id]).filter(Boolean)}
          lookup={lookup}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}
