"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle, Loader2, Wand2 } from "lucide-react";
import { useParams } from "next/navigation";
import { useMemo } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import type { ProgressEvent } from "@/lib/types";
import { useRunEvents } from "@/lib/useRunEvents";
import { cn, fmtDate } from "@/lib/utils";

const PHASES = ["explore", "generate", "write", "execute", "report", "done"] as const;

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const { events, connected, finished } = useRunEvents(runId);

  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId),
    refetchInterval: (q) =>
      ["succeeded", "failed", "cancelled"].includes(q.state.data?.status ?? "") ? false : 3000,
  });

  const terminal = ["succeeded", "failed", "cancelled"].includes(run.data?.status ?? "");
  // Enable the report fetch only when the run's persisted status is terminal —
  // the SSE `finished` flag can fire a beat before the API has written the
  // report, which would 404. (`finished` still drives the live UI below.)
  const report = useQuery({
    queryKey: ["report", runId],
    queryFn: () => api.getReport(runId),
    enabled: terminal,
  });

  const liveResults = useMemo(() => {
    const map = new Map<string, ProgressEvent>();
    for (const e of events) {
      if (e.phase === "execute" && e.status === "item_done") {
        map.set(String(e.data.test_case_id ?? e.data.test_case_name), e);
      }
    }
    return [...map.values()];
  }, [events]);

  const currentPhase = events.length ? events[events.length - 1].phase : null;

  return (
    <div className="stagger space-y-6">
      {/* Header */}
      <header className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="eyebrow">Run</div>
          <h1 className="mt-2 truncate text-2xl font-semibold tracking-tight">
            {run.data?.url ?? runId}
          </h1>
          <p className="mt-1.5 font-mono text-[11px] text-faint">
            {runId} · {run.data ? fmtDate(run.data.created_at) : ""} · {run.data?.model}
          </p>
        </div>
        {run.data && <StatusBadge status={run.data.status} />}
      </header>

      {/* Phase strip */}
      <div className="card">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-3">
          {PHASES.map((p, i) => {
            const seen = events.some((e) => e.phase === p);
            const active = currentPhase === p && !finished;
            return (
              <div key={p} className="flex items-center gap-2">
                <div
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-mono transition-colors",
                    seen ? "bg-elevated text-ink" : "text-faint"
                  )}
                >
                  {active ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
                  ) : seen ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-accent" />
                  ) : (
                    <Circle className="h-3.5 w-3.5" />
                  )}
                  {p}
                </div>
                {i < PHASES.length - 1 && <span className="h-px w-4 bg-line" />}
              </div>
            );
          })}
        </div>
        {run.data?.error && (
          <p className="mt-4 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">
            {run.data.error}
          </p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Console / activity */}
        <section className="card lg:col-span-2">
          <div className="panel-head">
            <h2 className="text-sm font-medium tracking-tight">Activity</h2>
            {!finished && connected && (
              <span className="flex items-center gap-1.5 font-mono text-[11px] text-accent">
                <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent" /> live
              </span>
            )}
          </div>
          <div className="scroll-thin max-h-72 space-y-1 overflow-y-auto rounded-lg border border-line-soft bg-bg/60 p-3 font-mono text-[11px] leading-relaxed">
            {events.map((e, i) => (
              <div key={`${e.seq}-${i}`} className="flex gap-2.5">
                <span className="shrink-0 text-faint">{String(e.phase).padEnd(8)}</span>
                <span className="text-muted">{e.message}</span>
              </div>
            ))}
            {events.length === 0 && <p className="text-faint">Waiting for events…</p>}
          </div>
        </section>

        {/* Results */}
        <section className="card lg:col-span-3">
          <div className="panel-head">
            <h2 className="text-sm font-medium tracking-tight">Test results</h2>
            {report.data && (
              <span className="font-mono text-[11px] text-muted tnum">
                {report.data.results.filter((r) => r.status === "passed").length} pass ·{" "}
                {report.data.results.filter((r) => r.status === "failed").length} fail
              </span>
            )}
          </div>

          {report.data ? (
            <div className="divide-y divide-line-soft">
              {report.data.results.map((r) => (
                <div key={r.test_case_id} className="flex items-center justify-between py-2.5">
                  <div className="min-w-0">
                    <div className="truncate text-sm">{r.test_case_name}</div>
                    {r.error_message && (
                      <div className="mt-0.5 truncate font-mono text-[11px] text-bad/80">{r.error_message}</div>
                    )}
                  </div>
                  <div className="ml-4 flex shrink-0 items-center gap-3">
                    {r.healed && (
                      <span className="flex items-center gap-1 font-mono text-[11px] text-accent">
                        <Wand2 className="h-3 w-3" /> healed
                      </span>
                    )}
                    <span className="font-mono text-[11px] text-faint tnum">{Math.round(r.duration_ms)}ms</span>
                    <StatusBadge status={r.status} />
                  </div>
                </div>
              ))}
            </div>
          ) : liveResults.length > 0 ? (
            <div className="divide-y divide-line-soft">
              {liveResults.map((e) => (
                <div key={e.seq} className="flex items-center justify-between py-2.5">
                  <span className="truncate text-sm">{String(e.data.test_case_name)}</span>
                  <StatusBadge status={String(e.data.result_status)} />
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-line py-10 text-center text-sm text-faint">
              {finished ? "No results." : "Tests will appear here as they run…"}
            </div>
          )}
        </section>
      </div>

      {/* Self-healing */}
      {report.data && report.data.healing_attempts.length > 0 && (
        <section className="card">
          <div className="panel-head">
            <h2 className="text-sm font-medium tracking-tight">Self-healing</h2>
            <span className="eyebrow">{report.data.healing_attempts.length} attempts</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {report.data.healing_attempts.map((h, i) => (
              <div key={i} className="rounded-xl border border-line bg-elevated/40 p-4">
                <div className="flex items-center justify-between">
                  <span className="truncate text-sm font-medium">{h.test_case_name}</span>
                  <span className="flex items-center gap-2">
                    <StatusBadge status={h.outcome} />
                    <span className="font-mono text-[11px] text-muted tnum">{Math.round(h.confidence * 100)}%</span>
                  </span>
                </div>
                <div className="mt-3 space-y-1 font-mono text-[11px]">
                  <div className="text-bad/80">- {h.original_selector}</div>
                  <div className="text-accent">+ {h.new_selector ?? "—"}</div>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-muted">{h.reasoning}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Flows */}
      {report.data && report.data.flows.length > 0 && (
        <section className="card">
          <div className="panel-head">
            <h2 className="text-sm font-medium tracking-tight">Identified flows</h2>
            <span className="eyebrow">{report.data.flows.length} flows</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {report.data.flows.map((f) => (
              <div key={f.id} className="rounded-xl border border-line bg-elevated/40 p-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{f.name}</span>
                  <span className="badge border-line bg-bg/60 font-mono text-muted">{f.priority}</span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">{f.description}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
