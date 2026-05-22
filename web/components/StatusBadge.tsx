import { cn } from "@/lib/utils";

type Tone = "good" | "bad" | "warn" | "info" | "muted";

const TONE: Record<string, Tone> = {
  succeeded: "good",
  passed: "good",
  healed: "good",
  failed: "bad",
  error: "bad",
  running: "info",
  queued: "info",
  skipped: "warn",
  refused: "warn",
  cancelled: "muted",
};

const STYLES: Record<Tone, string> = {
  good: "border-good/25 bg-good/10 text-good",
  bad: "border-bad/25 bg-bad/10 text-bad",
  warn: "border-warn/25 bg-warn/10 text-warn",
  info: "border-info/25 bg-info/10 text-info",
  muted: "border-line bg-elevated text-muted",
};

const DOT: Record<Tone, string> = {
  good: "bg-good",
  bad: "bg-bad",
  warn: "bg-warn",
  info: "bg-info",
  muted: "bg-faint",
};

export function StatusBadge({ status }: { status: string }) {
  const tone = TONE[status] ?? "muted";
  const live = status === "running" || status === "queued";
  return (
    <span className={cn("badge font-mono tracking-tight", STYLES[tone])}>
      <span className={cn("h-1.5 w-1.5 rounded-full", DOT[tone], live && "animate-pulse-dot")} />
      {status}
    </span>
  );
}
