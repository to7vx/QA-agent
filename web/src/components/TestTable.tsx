import { useState } from "react";
import { ChevronDown, ChevronRight, Sparkles } from "lucide-react";
import type { TestResult } from "../types";
import StatusBadge from "./StatusBadge";

interface Row {
  id: string;
  name: string;
  result: TestResult | null;
  running: boolean;
}

export default function TestTable({ rows }: { rows: Row[] }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});

  if (rows.length === 0) {
    return (
      <p className="py-6 text-center text-xs text-dim">
        Tests appear here as they are generated.
      </p>
    );
  }

  return (
    <div className="divide-y divide-edge/60">
      {rows.map((row) => {
        const status = row.running ? "running" : (row.result?.status ?? "pending");
        const hasDetail = !!(row.result?.error_message || row.result?.healing);
        const isOpen = open[row.id] ?? false;
        return (
          <div key={row.id}>
            <button
              onClick={() => hasDetail && setOpen((o) => ({ ...o, [row.id]: !isOpen }))}
              className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm ${
                hasDetail ? "cursor-pointer hover:bg-raise/40" : "cursor-default"
              }`}
            >
              <span className="w-4 shrink-0 text-dim">
                {hasDetail ? (
                  isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />
                ) : null}
              </span>
              <span className="min-w-0 flex-1 truncate">{row.name}</span>
              {row.result?.healed && (
                <span className="inline-flex items-center gap-1 rounded bg-heal/10 px-1.5 py-0.5 font-mono text-[10px] text-heal">
                  <Sparkles size={10} /> healed
                </span>
              )}
              {row.result != null && row.result.duration_ms > 0 && (
                <span className="shrink-0 font-mono text-[11px] text-dim">
                  {(row.result.duration_ms / 1000).toFixed(1)}s
                </span>
              )}
              <StatusBadge status={status} />
            </button>
            {isOpen && row.result && (
              <div className="space-y-2 bg-ink/50 px-11 py-3">
                {row.result.error_message && (
                  <pre className="overflow-x-auto whitespace-pre-wrap rounded border border-fail/20 bg-fail/5 p-2.5 font-mono text-[11px] leading-relaxed text-fail/90">
                    {row.result.error_message}
                  </pre>
                )}
                {row.result.healing && (
                  <div className="rounded border border-heal/20 bg-heal/5 p-2.5 font-mono text-[11px] leading-relaxed">
                    <div className="mb-1 flex items-center gap-1.5 text-heal">
                      <Sparkles size={11} />
                      self-healing · {row.result.healing.outcome} ·{" "}
                      {Math.round(row.result.healing.confidence * 100)}% confident
                    </div>
                    <div className="text-mut">
                      <span className="text-fail/80 line-through">
                        {row.result.healing.original_selector}
                      </span>
                      {row.result.healing.new_selector && (
                        <>
                          {" → "}
                          <span className="text-pass/90">{row.result.healing.new_selector}</span>
                        </>
                      )}
                    </div>
                  </div>
                )}
                {row.result.screenshot_path && (
                  <ScreenshotLink path={row.result.screenshot_path} />
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ScreenshotLink({ path }: { path: string }) {
  // Server mounts reports/screenshots at /screenshots — serve by trailing segments.
  const marker = "screenshots";
  const idx = path.replaceAll("\\", "/").lastIndexOf(marker + "/");
  if (idx < 0) return null;
  const rel = path.replaceAll("\\", "/").slice(idx + marker.length + 1);
  return (
    <a
      href={`/screenshots/${rel}`}
      target="_blank"
      rel="noreferrer"
      className="inline-block font-mono text-[11px] text-amber underline-offset-2 hover:underline"
    >
      view failure screenshot →
    </a>
  );
}
