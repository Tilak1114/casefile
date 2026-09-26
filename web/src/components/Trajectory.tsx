"use client";

import { useMemo, useState } from "react";

import { clock } from "@/lib/time";
import type { Bundle } from "@/lib/types";

type Team = NonNullable<Bundle["team"]>;
type TEvent = Team["events"][number];
type TTask = Team["tasks"][number];
type TReader = Team["readers"][number];
type TCall = Team["calls"][number];

const PURPOSE: Record<string, string> = {
  open: "Opening the claim file", next: "Deciding the next step", expert: "Deciding on the engineer", rule: "Ruling a dispute",
  brief: "Writing the case brief", plan: "Planning what to read", review: "Reviewing its readers' claims",
  report: "Reporting to the lead", answer: "Answering a request", absences: "Proposing absences",
  read: "Reading documents", repair: "Repairing refused claims",
};
const ROLE_OF = (actor: string) => actor.replace("-reader", "");
export type DocInfo = { doc_type: string; date: string | null; file_no: number; pages: number };
export type Stage = { key: string; title: string; detail: string; types: string[] };

// ---- geometry --------------------------------------------------------------------------------
const LABEL_W = 150;
const PLOT_W = 1080;
const AXIS_H = 26;
const TASK_H = 14;
const READER_H = 7;
const GAP = 4;
const LANE_PAD = 10;

type LaneKey = "lead" | "counsel" | "counsel-readers" | "engineer" | "engineer-readers" | "harness";
const LANES: { key: LaneKey; label: string; sub: string }[] = [
  { key: "lead", label: "Claim professional", sub: "lead · model" },
  { key: "counsel", label: "Defense counsel", sub: "role · model" },
  { key: "counsel-readers", label: "Counsel's readers", sub: "workers · model" },
  { key: "engineer", label: "Forensic engineer", sub: "role · model" },
  { key: "engineer-readers", label: "Engineer's readers", sub: "workers · model" },
  { key: "harness", label: "Harness", sub: "dispatcher · verifier" },
];

function laneOfActor(actor: string | null | undefined): LaneKey {
  if (actor === "lead" || actor === "counsel" || actor === "engineer") return actor;
  return "harness";
}

/** Greedy interval packing: each item gets the first row where it does not overlap. */
function pack<T extends { start: number; end: number | null }>(items: T[]): Map<T, number> {
  const rows: number[] = [];
  const out = new Map<T, number>();
  for (const it of [...items].sort((a, b) => a.start - b.start)) {
    const end = it.end ?? it.start;
    let r = rows.findIndex((e) => e <= it.start);
    if (r < 0) { r = rows.length; rows.push(end); } else rows[r] = end;
    out.set(it, r);
  }
  return out;
}


const CATEGORY: Record<string, { label: string; color: string; shape: "diamond" | "circle" | "square" }> = {
  "claim_file.opened": { label: "open / close", color: "var(--ink)", shape: "square" },
  "claim_file.closed": { label: "open / close", color: "var(--ink)", shape: "square" },
  "brief.submitted": { label: "open / close", color: "var(--ink)", shape: "square" },
  "counsel.assigned": { label: "assignment", color: "var(--accent)", shape: "diamond" },
  "work.assigned": { label: "assignment", color: "var(--accent)", shape: "diamond" },
  "expert.approved": { label: "assignment", color: "var(--accent)", shape: "diamond" },
  "expert.requested": { label: "assignment", color: "var(--accent)", shape: "diamond" },
  "expert.declined": { label: "assignment", color: "var(--accent)", shape: "diamond" },
  "scope.excluded": { label: "exclusion", color: "var(--muted)", shape: "diamond" },
  "report.submitted": { label: "report", color: "var(--ok)", shape: "circle" },
  "guard.hit": { label: "guard", color: "var(--pend)", shape: "square" },
  "task.expired": { label: "guard", color: "var(--pend)", shape: "square" },
  "absence.proposed": { label: "absence", color: "var(--ok)", shape: "diamond" },
  "absence.checked": { label: "absence", color: "var(--ok)", shape: "circle" },
};
const cat = (type: string) => CATEGORY[type] ?? { label: "collaboration", color: "var(--accent)", shape: "circle" as const };

function Mark({ x, y, type, dim, selected }: { x: number; y: number; type: string; dim: boolean; selected: boolean }) {
  const c = cat(type);
  const r = 5.5;
  const common = { fill: c.color, stroke: "var(--surface)", strokeWidth: 2, opacity: dim ? 0.18 : 1 };
  const ring = selected ? <circle cx={x} cy={y} r={r + 5} fill="none" stroke="var(--accent)" strokeWidth={2} /> : null;
  if (c.shape === "circle") return <g>{ring}<circle cx={x} cy={y} r={r} {...common} /></g>;
  if (c.shape === "square") return <g>{ring}<rect x={x - r} y={y - r} width={2 * r} height={2 * r} rx={1.5} {...common} /></g>;
  return <g>{ring}<path d={`M${x},${y - r - 1} L${x + r + 1},${y} L${x},${y + r + 1} L${x - r - 1},${y} Z`} {...common} /></g>;
}

type Selection = { kind: "event"; seq: number } | { kind: "task"; id: string } | { kind: "reader"; id: string };

export function Trajectory({ team, docs, stages }: { team: Team; docs: Record<string, DocInfo>; stages: Stage[] }) {
  const [sel, setSel] = useState<Selection>({ kind: "event", seq: team.events[0]?.seq ?? 1 });
  const [stage, setStage] = useState<string | null>(null);
  const [filter, setFilter] = useState<LaneKey | "all">("all");

  const highlight = useMemo(() => {
    const s = stages.find((x) => x.key === stage);
    return s ? new Set(s.types) : null;
  }, [stage, stages]);

  // lanes and rows
  const layout = useMemo(() => {
    const taskRows = new Map<TTask, number>();
    const readerRows = new Map<TReader, number>();
    const rowsIn: Record<LaneKey, number> = { lead: 1, counsel: 1, "counsel-readers": 1, engineer: 1, "engineer-readers": 1, harness: 1 };
    for (const role of ["lead", "counsel", "engineer"] as const) {
      const packed = pack(team.tasks.filter((t) => t.role === role));
      packed.forEach((r, t) => taskRows.set(t, r));
      rowsIn[role] = Math.max(1, ...Array.from(packed.values(), (r) => r + 1));
    }
    for (const role of ["counsel", "engineer"] as const) {
      const packed = pack(team.readers.filter((r) => r.role === role));
      packed.forEach((row, r) => readerRows.set(r, row));
      rowsIn[`${role}-readers`] = Math.max(1, ...Array.from(packed.values(), (r) => r + 1));
    }
    let y = AXIS_H;
    const lanes = LANES.map((l, i) => {
      const unit = l.key.endsWith("readers") ? READER_H : TASK_H;
      const h = Math.max(38, LANE_PAD * 2 + rowsIn[l.key] * (unit + GAP) + (l.key.endsWith("readers") ? 0 : 12));
      const lane = { ...l, y, h, shade: i % 2 === 1 };
      y += h;
      return lane;
    });
    return { lanes, height: y + 8, taskRows, readerRows };
  }, [team]);

  const laneBy = Object.fromEntries(layout.lanes.map((l) => [l.key, l])) as Record<LaneKey, (typeof layout.lanes)[number]>;
  const scale = PLOT_W / Math.max(team.duration_s, 1);
  const X = (t: number) => LABEL_W + t * scale;
  const eventY = (lane: LaneKey) => laneBy[lane].y + 12; // events ride along the top of their lane
  const ticks: number[] = [];
  for (let t = 0; t <= team.duration_s; t += 120) ticks.push(t);

  // stagger events published in the same second so their marks do not sit on top of each other
  const stagger = new Map<number, number>();
  const seenAt: Record<string, number> = {};
  for (const e of team.events) {
    const k = `${laneOfActor(e.sender)}:${Math.round(e.t)}`;
    seenAt[k] = (seenAt[k] ?? -1) + 1;
    stagger.set(e.seq, seenAt[k] * 9);
  }

  const eventBySeq = new Map(team.events.map((e) => [e.seq, e]));
  const taskById = new Map(team.tasks.map((t) => [t.id, t]));
  const readerById = new Map(team.readers.map((r) => [r.id, r]));
  const selectedTask = sel.kind === "task" ? taskById.get(sel.id) : undefined;
  const selectedReader = sel.kind === "reader" ? readerById.get(sel.id) : undefined;

  const visibleEvents = team.events.filter((e) => filter === "all" || laneOfActor(e.sender) === filter || laneOfActor(e.to) === filter);

  return (
    <div style={{ display: "grid", gap: "var(--s-4)" }}>
      {/* the process, stage by stage; a stage highlights its events on the timeline */}
      <div className="stages" role="list" aria-label="The process, stage by stage">
        {stages.map((s, i) => (
          <button key={s.key} role="listitem" className="stage" aria-pressed={stage === s.key}
                  onClick={() => setStage(stage === s.key ? null : s.key)} title="Highlight this stage's events on the timeline">
            <span className="stage-no">{i + 1}</span>
            <span className="stage-title">{s.title}</span>
            <span className="stage-detail">{s.detail}</span>
          </button>
        ))}
      </div>

      <figure className="card" style={{ margin: 0 }}>
        <div className="traj-scroll">
          <svg viewBox={`0 0 ${LABEL_W + PLOT_W + 48} ${layout.height}`} style={{ width: "100%", minWidth: LABEL_W + PLOT_W + 48, height: "auto" }}
               role="img" aria-label={`Timeline of run: ${team.events.length} events, ${team.tasks.length} tasks and ${team.readers.length} readers over ${clock(team.duration_s)}.`}>
            <defs>
              <marker id="msg" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M0 0L10 5L0 10z" fill="var(--faint)" />
              </marker>
            </defs>
            {layout.lanes.map((l) => (
              <g key={l.key}>
                <rect x={0} y={l.y} width={LABEL_W + PLOT_W + 48} height={l.h} fill={l.shade ? "var(--lane)" : "var(--surface)"} />
                <line x1={0} x2={LABEL_W + PLOT_W + 48} y1={l.y + l.h} y2={l.y + l.h} stroke="var(--line)" />
                <text x={12} y={l.y + 18} fontSize={12} fontWeight={600} fill="var(--ink)">{l.label}</text>
                <text x={12} y={l.y + 32} fontSize={10.5} fill="var(--muted)" fontFamily="var(--font-mono)">{l.sub}</text>
              </g>
            ))}
            <line x1={LABEL_W} x2={LABEL_W} y1={AXIS_H} y2={layout.height - 8} stroke="var(--line-strong)" />
            {ticks.map((t) => (
              <g key={t}>
                <line x1={X(t)} x2={X(t)} y1={AXIS_H} y2={layout.height - 8} stroke="var(--line)" strokeDasharray="2 4" />
                <text x={X(t)} y={16} textAnchor="middle" fontSize={11} fill="var(--muted)" fontFamily="var(--font-mono)">{clock(t)}</text>
              </g>
            ))}

            {/* tasks: one bar per task, in its role's lane */}
            {team.tasks.map((t) => {
              const lane = laneBy[laneOfActor(t.role)];
              const row = layout.taskRows.get(t) ?? 0;
              const y = lane.y + LANE_PAD + 12 + row * (TASK_H + GAP);
              const w = Math.max(3, ((t.end ?? t.start) - t.start) * scale);
              const trig = t.trigger_seq ? eventBySeq.get(t.trigger_seq) : undefined;
              const dim = highlight ? !(trig && highlight.has(trig.type)) : false;
              const on = sel.kind === "task" && sel.id === t.id;
              return (
                <g key={t.id} className="hit" onClick={() => setSel({ kind: "task", id: t.id })} opacity={dim ? 0.25 : 1}>
                  <rect x={X(t.start)} y={y} width={w} height={TASK_H} rx={3}
                        fill={t.state === "failed" ? "var(--bad-soft)" : "var(--accent-soft)"}
                        stroke={on ? "var(--accent)" : t.state === "failed" ? "var(--bad)" : "var(--accent)"} strokeWidth={on ? 2 : 1} />
                  {w > 70 && <text x={X(t.start) + 6} y={y + 10.5} fontSize={10} fill="var(--accent)" fontWeight={600}>{t.note || t.kind}</text>}
                  <rect x={X(t.start)} y={y - 3} width={Math.max(w, 10)} height={TASK_H + 6} fill="transparent">
                    <title>{`${t.role} task · ${t.kind}\n${clock(t.start)}–${clock(t.end ?? t.start)} · ${t.calls} model calls · $${t.cost_usd.toFixed(2)}\n${t.note}`}</title>
                  </rect>
                </g>
              );
            })}

            {/* readers: thin bars, packed into rows under their role */}
            {team.readers.map((r) => {
              const lane = laneBy[r.role === "engineer" ? "engineer-readers" : "counsel-readers"];
              const row = layout.readerRows.get(r) ?? 0;
              const y = lane.y + LANE_PAD + row * (READER_H + GAP);
              const on = sel.kind === "reader" && sel.id === r.id;
              const dim = highlight ? !highlight.has("reader") : false;
              return (
                <g key={r.id} className="hit" onClick={() => setSel({ kind: "reader", id: r.id })} opacity={dim ? 0.25 : 1}>
                  <rect x={X(r.start)} y={y} width={Math.max(3, (r.end - r.start) * scale)} height={READER_H} rx={2}
                        fill={r.refused > 0 ? "var(--pend)" : "var(--accent)"} opacity={on ? 1 : 0.75}
                        stroke={on ? "var(--ink)" : "none"} strokeWidth={1.5} />
                  <rect x={X(r.start)} y={y - 2} width={Math.max(8, (r.end - r.start) * scale)} height={READER_H + 4} fill="transparent">
                    <title>{`${r.role} reader · ${r.pages} pages · ${r.verified} verified, ${r.refused} refused\n${clock(r.start)}–${clock(r.end)}`}</title>
                  </rect>
                </g>
              );
            })}

            {/* events: a mark on the sender's lane; a message to another lane draws a line to it */}
            {team.events.map((e) => {
              const from = laneOfActor(e.sender);
              const to = e.to ? laneOfActor(e.to) : null;
              const x = X(e.t) + (stagger.get(e.seq) ?? 0);
              const y1 = eventY(from);
              const dim = highlight ? !highlight.has(e.type) : false;
              const on = sel.kind === "event" && sel.seq === e.seq;
              return (
                <g key={e.seq} className="hit" onClick={() => setSel({ kind: "event", seq: e.seq })}>
                  {to && to !== from && (
                    <line x1={x} x2={x} y1={y1 + (eventY(to) > y1 ? 7 : -7)} y2={eventY(to) + (eventY(to) > y1 ? -8 : 8)}
                          stroke="var(--faint)" strokeWidth={1.2} markerEnd="url(#msg)" opacity={dim ? 0.15 : 0.9} />
                  )}
                  <Mark x={x} y={y1} type={e.type} dim={dim} selected={on} />
                  <circle cx={x} cy={y1} r={11} fill="transparent">
                    <title>{`#${e.seq} ${e.type} · ${e.sender}${e.to ? ` → ${e.to}` : ""} · ${clock(e.t)}\n${e.summary.slice(0, 200)}`}</title>
                  </circle>
                </g>
              );
            })}
          </svg>
        </div>
        <figcaption className="traj-legend">
          {["assignment", "report", "exclusion", "guard", "absence", "open / close"].map((label) => {
            const entry = Object.values(CATEGORY).find((c) => c.label === label)!;
            return (
              <span key={label}>
                <svg width={14} height={14} aria-hidden><Mark x={7} y={7} type={Object.keys(CATEGORY).find((k) => CATEGORY[k].label === label)!} dim={false} selected={false} /></svg>
                {label}
                <span hidden>{entry.color}</span>
              </span>
            );
          })}
          <span><svg width={22} height={10} aria-hidden><rect x={1} y={1} width={20} height={8} rx={2} fill="var(--accent-soft)" stroke="var(--accent)" /></svg>task</span>
          <span><svg width={22} height={10} aria-hidden><rect x={1} y={2} width={20} height={6} rx={2} fill="var(--accent)" opacity={0.75} /></svg>reader</span>
          <span><svg width={22} height={10} aria-hidden><rect x={1} y={2} width={20} height={6} rx={2} fill="var(--pend)" opacity={0.75} /></svg>reader with a refused claim</span>
          <span style={{ color: "var(--muted)" }}>Click any mark or bar for detail. Time is minutes since the claim file opened.</span>
        </figcaption>
      </figure>

      <div className="grid-2" style={{ alignItems: "start" }}>
        <section className="card pad" style={{ display: "grid", gap: "var(--s-3)" }} aria-live="polite">
          {sel.kind === "event" && <EventDetail e={eventBySeq.get(sel.seq)!} team={team} onSelect={setSel} docs={docs} />}
          {selectedTask && <TaskDetail t={selectedTask} team={team} onSelect={setSel} />}
          {selectedReader && <ReaderDetail r={selectedReader} docs={docs} onSelect={setSel} team={team} />}
        </section>
        <section className="card" style={{ display: "grid" }}>
          <div className="board-bar" style={{ borderRadius: "var(--r-2) var(--r-2) 0 0" }}>
            <strong style={{ fontSize: 13 }}>Event log</strong>
            <div className="seg" role="group" aria-label="Filter events by lane">
              {(["all", "lead", "counsel", "engineer", "harness"] as const).map((k) => (
                <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{k}</button>
              ))}
            </div>
            <span className="board-count">{visibleEvents.length} events</span>
          </div>
          <div className="table-wrap" style={{ maxHeight: 420, overflowY: "auto" }}>
            <table className="data">
              <thead><tr><th>#</th><th>Time</th><th>Event</th><th>From → to</th></tr></thead>
              <tbody>
                {visibleEvents.map((e) => (
                  <tr key={e.seq} className="clickable" onClick={() => setSel({ kind: "event", seq: e.seq })}
                      style={sel.kind === "event" && sel.seq === e.seq ? { background: "var(--accent-soft)" } : undefined}>
                    <td className="num">{e.seq}</td>
                    <td className="date">{clock(e.t)}</td>
                    <td><span className="mono" style={{ color: cat(e.type).color }}>{e.type}</span></td>
                    <td style={{ whiteSpace: "nowrap", color: "var(--muted)" }}>{e.sender}{e.to ? ` → ${e.to}` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="section">
        <h2>What the agents were thinking</h2>
        <p>
          Every decision the lead, counsel and the engineer made, in order: the model&apos;s summary of its own reasoning, then the typed
          answer the harness acted on. {team.reasoning_recorded ? "" : "This run did not record reasoning summaries; only the decisions are shown."}
        </p>
        <div style={{ display: "grid", gap: 6 }}>
          {team.calls.filter((c) => !c.actor.endsWith("-reader")).map((c) => (
            <CallCard key={c.id} call={c} onTask={c.task_id ? () => { setSel({ kind: "task", id: c.task_id! }); window.scrollTo({ top: 0, behavior: "smooth" }); } : undefined} />
          ))}
        </div>
      </section>
    </div>
  );
}

function Jump({ label, onClick }: { label: string; onClick: () => void }) {
  return <button className="link-button" onClick={onClick}>{label}</button>;
}

function EventDetail({ e, team, onSelect, docs }: { e: TEvent; team: Team; onSelect: (s: Selection) => void; docs: Record<string, DocInfo> }) {
  const cause = e.causation_seq ? team.events.find((x) => x.seq === e.causation_seq) : undefined;
  const effects = team.events.filter((x) => x.causation_seq === e.seq);
  const tasks = team.tasks.filter((t) => t.trigger_seq === e.seq);
  // the decision that produced this event: the sender's latest model call that had answered by then
  const why = ["lead", "counsel", "engineer"].includes(e.sender)
    ? team.calls.filter((c) => c.actor === e.sender && c.t <= e.t + 1).sort((a, b) => b.t - a.t)[0]
    : undefined;
  return (
    <>
      <div className="eyebrow">Event #{e.seq} · {clock(e.t)}</div>
      <h2 style={{ fontSize: "var(--t-16)" }}><span className="mono" style={{ color: cat(e.type).color }}>{e.type}</span></h2>
      <dl className="kv">
        <dt>From</dt><dd>{e.sender}</dd>
        <dt>To</dt><dd>{e.to ?? "everyone subscribed"}</dd>
        {cause && <><dt>Caused by</dt><dd><Jump label={`#${cause.seq} ${cause.type}`} onClick={() => onSelect({ kind: "event", seq: cause.seq })} /></dd></>}
        {e.subjects > 0 && <><dt>Refers to</dt><dd>{e.subjects} {e.type === "report.submitted" || e.type === "brief.submitted" ? "claims" : "documents"}</dd></>}
      </dl>
      {e.summary && <p style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{e.summary}</p>}
      {why && (
        <div style={{ display: "grid", gap: 6 }}>
          <div className="eyebrow">Why: the decision behind it</div>
          <CallCard call={why} open />
        </div>
      )}
      {e.document_ids.length > 0 && <DocList ids={e.document_ids} docs={docs} />}
      {(tasks.length > 0 || effects.length > 0) && (
        <div style={{ display: "grid", gap: 4, fontSize: 13 }}>
          <div className="eyebrow">What it caused</div>
          {tasks.map((t) => <div key={t.id}>task: <Jump label={`${t.role} · ${t.note || t.kind}`} onClick={() => onSelect({ kind: "task", id: t.id })} /></div>)}
          {effects.map((x) => <div key={x.seq}>event: <Jump label={`#${x.seq} ${x.type}`} onClick={() => onSelect({ kind: "event", seq: x.seq })} /></div>)}
        </div>
      )}
    </>
  );
}

function TaskDetail({ t, team, onSelect }: { t: TTask; team: Team; onSelect: (s: Selection) => void }) {
  const readers = team.readers.filter((r) => r.task_id === t.id);
  const thinking = team.calls.filter((c) => c.task_id === t.id && !c.actor.endsWith("-reader"));
  const trig = t.trigger_seq ? team.events.find((e) => e.seq === t.trigger_seq) : undefined;
  const out = team.events.filter((e) => e.sender === t.role && e.t >= t.start && e.t <= (t.end ?? t.start) + 1);
  const pages = readers.reduce((a, r) => a + r.pages, 0);
  return (
    <>
      <div className="eyebrow">Task · {t.role}</div>
      <h2 style={{ fontSize: "var(--t-16)" }}>{t.kind}</h2>
      <dl className="kv">
        <dt>When</dt><dd className="num">{clock(t.start)} – {clock(t.end ?? t.start)}</dd>
        <dt>Outcome</dt><dd><span className={`pill ${t.state === "done" ? "ok" : t.state === "failed" ? "bad" : "pend"}`}>{t.state}</span> {t.note}</dd>
        {trig && <><dt>Woken by</dt><dd><Jump label={`#${trig.seq} ${trig.type} from ${trig.sender}`} onClick={() => onSelect({ kind: "event", seq: trig.seq })} /></dd></>}
        <dt>Model calls</dt><dd className="num">{t.calls} · ${t.cost_usd.toFixed(2)}</dd>
        {readers.length > 0 && <><dt>Readers</dt><dd className="num">{readers.length} · {pages} pages · {readers.reduce((a, r) => a + r.verified, 0)} verified, {readers.reduce((a, r) => a + r.refused, 0)} refused</dd></>}
      </dl>
      {thinking.length > 0 && (
        <div style={{ display: "grid", gap: 6 }}>
          <div className="eyebrow">Its thinking, call by call</div>
          {thinking.map((c, i) => <CallCard key={c.id} call={c} open={i === thinking.length - 1} />)}
        </div>
      )}
      {out.length > 0 && (
        <div style={{ display: "grid", gap: 4, fontSize: 13 }}>
          <div className="eyebrow">Published</div>
          {out.map((e) => <div key={e.seq}><Jump label={`#${e.seq} ${e.type}`} onClick={() => onSelect({ kind: "event", seq: e.seq })} /></div>)}
        </div>
      )}
      {readers.length > 0 && (
        <div style={{ display: "grid", gap: 4, fontSize: 13 }}>
          <div className="eyebrow">Readers it started</div>
          {readers.map((r) => (
            <div key={r.id} className="num">
              <Jump label={`${clock(r.start)} · ${r.pages} pages`} onClick={() => onSelect({ kind: "reader", id: r.id })} /> · {r.verified} verified{r.refused ? `, ${r.refused} refused` : ""}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function ReaderDetail({ r, docs, onSelect, team }: { r: TReader; docs: Record<string, DocInfo>; onSelect: (s: Selection) => void; team: Team }) {
  const task = team.tasks.find((t) => t.id === r.task_id);
  return (
    <>
      <div className="eyebrow">Reader · {r.role}</div>
      <h2 style={{ fontSize: "var(--t-16)" }}>{r.pages} pages, {r.verified} verified claims{r.refused ? `, ${r.refused} refused` : ""}</h2>
      <dl className="kv">
        <dt>When</dt><dd className="num">{clock(r.start)} – {clock(r.end)} ({Math.round(r.end - r.start)} s)</dd>
        {task && <><dt>Started by</dt><dd><Jump label={`${task.role} task · ${task.kind}`} onClick={() => onSelect({ kind: "task", id: task.id })} /></dd></>}
        <dt>Focus</dt><dd>{r.focus}</dd>
      </dl>
      <p style={{ fontSize: 12, color: "var(--muted)" }}>The harness logged these pages as read before the model ran; every claim was then checked against them.</p>
      {team.calls.filter((c) => c.ref === r.id).map((c, i) => <CallCard key={c.id} call={c} open={i === 0} />)}
      <DocList ids={r.document_ids} docs={docs} />
    </>
  );
}

function DocList({ ids, docs }: { ids: string[]; docs: Record<string, DocInfo> }) {
  return (
    <div className="table-wrap" style={{ maxHeight: 220, overflowY: "auto", border: "1px solid var(--line)", borderRadius: "var(--r-2)" }}>
      <table className="data">
        <thead><tr><th>Document</th><th>Type</th><th>Date</th><th>Pages</th></tr></thead>
        <tbody>
          {ids.map((id) => {
            const d = docs[id];
            return (
              <tr key={id}>
                <td className="mono" style={{ whiteSpace: "nowrap" }}>PDF {id.split(":")[1]} · {id.split(":")[2]}</td>
                <td>{d?.doc_type.replaceAll("_", " ") ?? "—"}</td>
                <td className="date">{d?.date ?? "—"}</td>
                <td className="num">{d?.pages ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** The provider's reasoning summary: "**Heading**" lines become small headings. */
function Reasoning({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  const out: React.ReactNode[] = [];
  for (let i = 0; i < parts.length; i++) {
    const chunk = parts[i].trim();
    if (!chunk) continue;
    out.push(i % 2 === 1
      ? <div key={i} className="think-h">{chunk}</div>
      : <p key={i} className="think-p">{chunk}</p>);
  }
  return <div className="think">{out}</div>;
}

function Decision({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined || value === "") return <span style={{ color: "var(--faint)" }}>—</span>;
  if (typeof value !== "object") return <span>{String(value)}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span style={{ color: "var(--faint)" }}>none</span>;
    if (value.every((v) => typeof v !== "object")) return <span>{value.join(", ")}</span>;
    return <ol className="dec-list">{value.map((v, i) => <li key={i}><Decision value={v} depth={depth + 1} /></li>)}</ol>;
  }
  return (
    <dl className="kv dec">
      {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}><dt>{k.replaceAll("_", " ")}</dt><dd><Decision value={v} depth={depth + 1} /></dd></div>
      ))}
    </dl>
  );
}

export function CallCard({ call, open = false, onTask }: { call: TCall; open?: boolean; onTask?: () => void }) {
  return (
    <details className="call" open={open}>
      <summary>
        <span className="call-who">{ROLE_OF(call.actor)}{call.actor.endsWith("-reader") ? " reader" : ""}</span>
        <span className="call-what">{PURPOSE[call.purpose] ?? call.purpose}</span>
        <span className="call-meta num">{clock(call.t)} · {call.reasoning_tokens.toLocaleString()} reasoning tokens · ${call.cost_usd.toFixed(3)}</span>
      </summary>
      <div className="call-body">
        <div className="eyebrow">Reasoning (the model&apos;s own summary)</div>
        {call.reasoning ? <Reasoning text={call.reasoning} /> : <p className="think-p" style={{ color: "var(--muted)" }}>Not recorded for this run.</p>}
        <div className="eyebrow">{call.actor.endsWith("-reader") ? "What it returned (counts)" : "What it decided"}</div>
        <Decision value={call.decision} />
        {onTask && <button className="link-button" style={{ fontSize: 12 }} onClick={onTask}>Show its task on the timeline</button>}
      </div>
    </details>
  );
}
