"use client";

import type { GroupBar, SeriesPoint, Slice } from "@/lib/run-charts";

const PAD = { l: 40, r: 8, t: 16, b: 22 };

export function DonutChart({ slices, total }: { slices: Slice[]; total: number }) {
  const size = 168;
  const cx = size / 2;
  const cy = size / 2;
  const r = 58;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="mx-auto size-40" role="img">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border)" strokeWidth="14" />
      {slices.map((slice) => {
        const len = total ? (slice.value / total) * c : 0;
        const dash = `${len} ${c - len}`;
        const el = (
          <circle
            key={slice.key}
            className="chart-arc"
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={slice.color}
            strokeWidth="14"
            strokeDasharray={dash}
            strokeDashoffset={-offset}
            strokeLinecap="butt"
            transform={`rotate(-90 ${cx} ${cy})`}
          >
            <title>{`${slice.label} · ${slice.value}`}</title>
          </circle>
        );
        offset += len;
        return el;
      })}
      <text x={cx} y={cy - 6} textAnchor="middle" className="fill-ink" fontSize="22" fontWeight="600">
        {total}
      </text>
      <text x={cx} y={cy + 14} textAnchor="middle" className="fill-muted-foreground" fontSize="10">
        runs
      </text>
    </svg>
  );
}

export function BarChart({
  bars,
  format,
}: {
  bars: GroupBar[];
  format: (value: number) => string;
}) {
  const w = 520;
  const h = 200;
  const innerW = w - PAD.l - PAD.r;
  const innerH = h - PAD.t - PAD.b;
  const max = Math.max(...bars.map((b) => b.value), 0.0001);
  const gap = 8;
  const bw = bars.length ? Math.min(56, (innerW - gap * (bars.length - 1)) / bars.length) : 0;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-full min-h-0 w-full" role="img">
      <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={h - PAD.b} stroke="var(--border)" />
      <line x1={PAD.l} y1={h - PAD.b} x2={w - PAD.r} y2={h - PAD.b} stroke="var(--border)" />
      {bars.map((bar, i) => {
        const bh = (bar.value / max) * innerH;
        const x = PAD.l + i * (bw + gap) + (innerW - bars.length * bw - gap * (bars.length - 1)) / 2;
        const y = h - PAD.b - bh;
        return (
          <g key={bar.key}>
            <rect
              className="chart-bar"
              x={x}
              y={y}
              width={bw}
              height={Math.max(bh, bar.value > 0 ? 2 : 0)}
              fill={bar.color}
            >
              <title>{`${bar.label} · ${format(bar.value)}`}</title>
            </rect>
            <text
              x={x + bw / 2}
              y={Math.max(y - 4, 10)}
              textAnchor="middle"
              className="fill-ink"
              fontSize="9"
            >
              {format(bar.value)}
            </text>
            <text
              x={x + bw / 2}
              y={h - PAD.b + 14}
              textAnchor="middle"
              className="fill-muted-foreground"
              fontSize="9"
            >
              {truncate(bar.label, 10)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function LineChart({
  points,
  format,
  gradientId = "chart-area",
}: {
  points: SeriesPoint[];
  format: (value: number) => string;
  gradientId?: string;
}) {
  const w = 640;
  const h = 220;
  const innerW = w - PAD.l - PAD.r;
  const innerH = h - PAD.t - PAD.b;
  if (points.length === 0) return null;
  const ys = points.map((p) => p.value);
  const min = Math.min(...ys);
  const max = Math.max(...ys);
  const span = max - min || 1;
  const coords = points.map((p, i) => {
    const x = PAD.l + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
    const y = PAD.t + innerH - ((p.value - min) / span) * innerH;
    return { x, y, p };
  });
  const line = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const area = `${line} L${coords.at(-1)!.x},${h - PAD.b} L${coords[0].x},${h - PAD.b} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-full min-h-0 w-full" role="img">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--active)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--active)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={h - PAD.b} stroke="var(--border)" />
      <line x1={PAD.l} y1={h - PAD.b} x2={w - PAD.r} y2={h - PAD.b} stroke="var(--border)" />
      <text x={PAD.l - 6} y={PAD.t + 4} textAnchor="end" className="fill-muted-foreground" fontSize="9">
        {format(max)}
      </text>
      <text x={PAD.l - 6} y={h - PAD.b} textAnchor="end" className="fill-muted-foreground" fontSize="9">
        {format(min)}
      </text>
      <path className="chart-area" d={area} fill={`url(#${gradientId})`} />
      <path className="chart-line" pathLength={1} d={line} fill="none" stroke="var(--active)" strokeWidth="2" />
      {coords.map((c) => (
        <circle key={c.p.id} cx={c.x} cy={c.y} r="3.5" fill="var(--card)" stroke="var(--active)" strokeWidth="1.5">
          <title>{`${c.p.label} · ${format(c.p.value)}`}</title>
        </circle>
      ))}
      {coords.map((c, i) =>
        i === 0 || i === coords.length - 1 || coords.length < 8 ? (
          <text key={`${c.p.id}-l`} x={c.x} y={h - 8} textAnchor="middle" className="fill-muted-foreground" fontSize="9">
            {c.p.label.replace(/^RUN-/, "")}
          </text>
        ) : null,
      )}
    </svg>
  );
}

export function StackedBarChart({
  bars,
}: {
  bars: {
    key: string;
    label: string;
    parts: { key: string; label: string; value: number; color: string }[];
  }[];
}) {
  const w = 520;
  const h = 200;
  const innerW = w - PAD.l - PAD.r;
  const innerH = h - PAD.t - PAD.b;
  const totals = bars.map((bar) => bar.parts.reduce((sum, part) => sum + part.value, 0));
  const max = Math.max(...totals, 1);
  const gap = 10;
  const bw = bars.length ? Math.min(56, (innerW - gap * (bars.length - 1)) / bars.length) : 0;
  const offset = bars.length ? (innerW - bars.length * bw - gap * (bars.length - 1)) / 2 : 0;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-full min-h-0 w-full" role="img">
      <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={h - PAD.b} stroke="var(--border)" />
      <line x1={PAD.l} y1={h - PAD.b} x2={w - PAD.r} y2={h - PAD.b} stroke="var(--border)" />
      {bars.map((bar, i) => {
        const x = PAD.l + offset + i * (bw + gap);
        let y = h - PAD.b;
        return (
          <g key={bar.key}>
            {bar.parts.map((part) => {
              const bh = (part.value / max) * innerH;
              y -= bh;
              if (part.value <= 0) return null;
              return (
                <rect key={part.key} className="chart-bar" x={x} y={y} width={bw} height={Math.max(bh, 2)} fill={part.color}>
                  <title>{`${bar.label} · ${part.label} · ${part.value}`}</title>
                </rect>
              );
            })}
            <text x={x + bw / 2} y={h - PAD.b + 14} textAnchor="middle" className="fill-muted-foreground" fontSize="9">
              {truncate(bar.label, 10)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function truncate(value: string, n: number): string {
  return value.length > n ? `${value.slice(0, n - 1)}…` : value;
}
