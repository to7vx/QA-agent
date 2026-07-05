const styles: Record<string, string> = {
  passed: "bg-pass/10 text-pass",
  failed: "bg-fail/10 text-fail",
  error: "bg-fail/10 text-fail",
  skipped: "bg-mut/10 text-mut",
  running: "bg-amber/10 text-amber",
  pending: "bg-dim/10 text-dim",
  finished: "bg-pass/10 text-pass",
  cancelled: "bg-mut/10 text-mut",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[11px] ${
        styles[status] ?? "bg-dim/10 text-dim"
      }`}
    >
      {status === "running" && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber" />
      )}
      {status}
    </span>
  );
}
