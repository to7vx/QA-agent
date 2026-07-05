interface Props {
  passRate: number; // 0–100
  size?: number;
  label?: boolean;
}

/** SVG pass-rate ring: green arc over a faint track. */
export default function PassRing({ passRate, size = 56, label = true }: Props) {
  const stroke = size >= 48 ? 5 : 3.5;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const filled = (passRate / 100) * c;
  const color =
    passRate >= 100 ? "var(--color-pass)" : passRate >= 50 ? "var(--color-amber)" : "var(--color-fail)";

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-edge)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${c - filled}`}
        />
      </svg>
      {label && (
        <span className="absolute font-mono text-[11px] text-fg">
          {Math.round(passRate)}%
        </span>
      )}
    </div>
  );
}
