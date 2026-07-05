/** Hand-rolled SVG charts — no chart library, tiny bundle. */

interface TrendPoint {
  pass_rate: number;
  url: string;
  date: string | null;
}

export function TrendChart({ points }: { points: TrendPoint[] }) {
  const w = 640;
  const h = 160;
  const pad = 8;
  if (points.length === 0) return null;
  const xs = (i: number) =>
    points.length === 1 ? w / 2 : pad + (i * (w - 2 * pad)) / (points.length - 1);
  const ys = (rate: number) => pad + ((100 - rate) * (h - 2 * pad)) / 100;

  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${xs(i)},${ys(p.pass_rate)}`).join(" ");
  const area = `${line} L${xs(points.length - 1)},${h - pad} L${xs(0)},${h - pad} Z`;

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="w-full"
      role="img"
      aria-label="Pass rate trend across runs"
    >
      {[0, 50, 100].map((tick) => (
        <g key={tick}>
          <line
            x1={pad}
            x2={w - pad}
            y1={ys(tick)}
            y2={ys(tick)}
            stroke="var(--color-edge)"
            strokeWidth="1"
            strokeDasharray={tick === 50 ? "3 5" : undefined}
          />
          <text x={w - pad} y={ys(tick) - 3} textAnchor="end" fontSize="9" fill="var(--color-dim)">
            {tick}%
          </text>
        </g>
      ))}
      <path d={area} fill="var(--color-amber)" opacity="0.08" />
      <path d={line} fill="none" stroke="var(--color-amber)" strokeWidth="2" strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={xs(i)}
          cy={ys(p.pass_rate)}
          r="3"
          fill={p.pass_rate >= 100 ? "var(--color-pass)" : p.pass_rate >= 50 ? "var(--color-amber)" : "var(--color-fail)"}
        >
          <title>{`${p.url} — ${Math.round(p.pass_rate)}%`}</title>
        </circle>
      ))}
    </svg>
  );
}

export function BarList({
  items,
}: {
  items: { label: string; value: number; max: number; hint?: string }[];
}) {
  return (
    <div className="space-y-2.5">
      {items.map((item) => (
        <div key={item.label}>
          <div className="mb-1 flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate text-xs text-fg">{item.label}</span>
            <span className="shrink-0 font-mono text-[10px] text-dim">
              {item.hint ?? item.value}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-raise">
            <div
              className="h-full rounded-full bg-fail/80"
              style={{ width: `${Math.max(6, (item.value / Math.max(item.max, 1)) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function HealingDonut({
  healing,
}: {
  healing: { healed: number; refused: number; failed: number; error: number };
}) {
  const entries = [
    { key: "healed", value: healing.healed, color: "var(--color-heal)" },
    { key: "refused", value: healing.refused, color: "var(--color-amber)" },
    { key: "failed", value: healing.failed, color: "var(--color-fail)" },
    { key: "error", value: healing.error, color: "var(--color-dim)" },
  ].filter((e) => e.value > 0);
  const total = entries.reduce((sum, e) => sum + e.value, 0);
  if (total === 0) {
    return <p className="text-xs text-dim">No healing attempts yet.</p>;
  }

  const size = 120;
  const r = 44;
  const c = 2 * Math.PI * r;
  let offset = 0;

  return (
    <div className="flex items-center gap-5">
      <svg width={size} height={size} className="-rotate-90 shrink-0" aria-hidden="true">
        {entries.map((e) => {
          const frac = e.value / total;
          const seg = (
            <circle
              key={e.key}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={e.color}
              strokeWidth="12"
              strokeDasharray={`${frac * c - 2} ${c - frac * c + 2}`}
              strokeDashoffset={-offset * c}
            />
          );
          offset += frac;
          return seg;
        })}
      </svg>
      <ul className="space-y-1.5">
        {entries.map((e) => (
          <li key={e.key} className="flex items-center gap-2 text-xs text-mut">
            <span className="h-2 w-2 rounded-full" style={{ background: e.color }} />
            <span className="font-mono">{e.value}</span> {e.key}
          </li>
        ))}
      </ul>
    </div>
  );
}
