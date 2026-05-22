import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string | number;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div className="card group relative overflow-hidden">
      {/* corner glow on accented cards */}
      {accent && (
        <span className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-accent/15 blur-2xl" />
      )}
      <div className="eyebrow">{label}</div>
      <div
        className={cn(
          "mt-3 font-mono text-[2rem] font-semibold leading-none tnum tracking-tight",
          accent ? "text-accent" : "text-ink"
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-2 text-xs text-muted">{hint}</div>}
    </div>
  );
}
