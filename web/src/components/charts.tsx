// Small single-series SVG charts, server-rendered. One series each: no legend; the title names it.
// Every mark carries a <title> so hovering shows its value; the Harness screen's turn table is the table view.

type Point = { x: number; y: number; label: string };

const W = 460;
const H = 180;
const PAD = { l: 44, r: 30, t: 12, b: 26 };

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / p) * p;
}

function Axes({ maxY, xs, fmt }: { maxY: number; xs: number[]; fmt: (v: number) => string }) {
  const ticks = [0, maxY / 2, maxY];
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const xLabels = xs.length > 1 ? [xMin, Math.round((xMin + xMax) / 2), xMax] : [xMin];
  return (
    <g>
      {ticks.map((t) => {
        const y = PAD.t + ih - (t / maxY) * ih;
        return (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y} y2={y} stroke="var(--line)" strokeWidth={1} />
            <text x={PAD.l - 6} y={y + 4} textAnchor="end" fontSize={11} fill="var(--muted)" className="num">{fmt(t)}</text>
          </g>
        );
      })}
      {xLabels.map((x) => {
        const px = PAD.l + (xs.length > 1 ? ((x - xMin) / (xMax - xMin)) * iw : iw / 2);
        const anchor = x === xMax && xs.length > 1 ? "end" : x === xMin && xs.length > 1 ? "start" : "middle";
        return <text key={x} x={px} y={H - 6} textAnchor={anchor} fontSize={11} fill="var(--muted)">turn {x}</text>;
      })}
    </g>
  );
}

export function LineChart({ title, points, fmt = (v) => v.toLocaleString() }: { title: string; points: Point[]; fmt?: (v: number) => string }) {
  if (points.length === 0) return <div className="empty">No data yet.</div>;
  const maxY = niceMax(Math.max(...points.map((p) => p.y)));
  const xs = points.map((p) => p.x);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const px = (x: number) => PAD.l + (xMax > xMin ? ((x - xMin) / (xMax - xMin)) * iw : iw / 2);
  const py = (y: number) => PAD.t + ih - (y / maxY) * ih;
  const d = points.map((p, i) => `${i ? "L" : "M"}${px(p.x).toFixed(1)},${py(p.y).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  return (
    <figure className="card pad" style={{ margin: 0, display: "grid", gap: 8 }}>
      <figcaption style={{ fontWeight: 600, fontSize: 13 }}>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }} role="img" aria-label={`${title}: ${fmt(last.y)} at turn ${last.x}`}>
        <Axes maxY={maxY} xs={xs} fmt={fmt} />
        <path d={`${d} L${px(last.x)},${py(0)} L${px(points[0].x)},${py(0)} Z`} fill="var(--accent)" opacity={0.08} />
        <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" />
        {points.map((p) => (
          <g key={p.x}>
            <circle cx={px(p.x)} cy={py(p.y)} r={p === last ? 4.5 : 3} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />
            <circle cx={px(p.x)} cy={py(p.y)} r={10} fill="transparent"><title>{p.label}</title></circle>
          </g>
        ))}
        <text x={px(last.x) - 6} y={py(last.y) - 9} textAnchor="end" fontSize={12} fontWeight={600} fill="var(--ink)" className="num">{fmt(last.y)}</text>
      </svg>
    </figure>
  );
}

export function BarChart({ title, points, fmt = (v) => v.toLocaleString(), note }: { title: string; points: Point[]; fmt?: (v: number) => string; note?: string }) {
  if (points.length === 0) return <div className="empty">No data yet.</div>;
  const maxY = niceMax(Math.max(...points.map((p) => p.y)));
  const xs = points.map((p) => p.x);
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const slot = iw / points.length;
  const bw = Math.max(3, slot - 2);
  return (
    <figure className="card pad" style={{ margin: 0, display: "grid", gap: 8 }}>
      <figcaption style={{ fontWeight: 600, fontSize: 13 }}>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }} role="img" aria-label={title}>
        <Axes maxY={maxY} xs={xs} fmt={fmt} />
        {points.map((p, i) => {
          const h = (p.y / maxY) * ih;
          const x = PAD.l + i * slot + (slot - bw) / 2;
          const y = PAD.t + ih - h;
          return (
            <g key={p.x}>
              <path d={`M${x},${PAD.t + ih} V${y + Math.min(4, h)} Q${x},${y} ${x + Math.min(4, bw / 2)},${y} H${x + bw - Math.min(4, bw / 2)} Q${x + bw},${y} ${x + bw},${y + Math.min(4, h)} V${PAD.t + ih} Z`} fill="var(--accent)" />
              <rect x={PAD.l + i * slot} y={PAD.t} width={slot} height={ih} fill="transparent"><title>{p.label}</title></rect>
            </g>
          );
        })}
      </svg>
      {note && <p style={{ fontSize: 12, color: "var(--muted)" }}>{note}</p>}
    </figure>
  );
}
