"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, FileCode2, GitBranch } from "lucide-react";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { api } from "@/lib/api";
import type { TestCase } from "@/lib/types";
import { cn, fmtDate } from "@/lib/utils";

const PRIORITY: Record<string, string> = {
  high: "border-bad/25 bg-bad/10 text-bad",
  medium: "border-warn/25 bg-warn/10 text-warn",
  low: "border-line bg-elevated text-muted",
};

const TERMINAL = ["succeeded", "failed"];

export default function TestsPage() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.listRuns });
  const [runId, setRunId] = useState<string | null>(null);

  // Only finished runs have a report with flows/tests.
  const finishedRuns = (runs.data ?? []).filter((r) => TERMINAL.includes(r.status));

  // Default to the latest finished run.
  useEffect(() => {
    if (runId || finishedRuns.length === 0) return;
    const done = finishedRuns.find((r) => r.status === "succeeded") ?? finishedRuns[0];
    if (done) setRunId(done.id);
  }, [finishedRuns, runId]);

  const report = useQuery({
    queryKey: ["report", runId],
    queryFn: () => api.getReport(runId!),
    enabled: !!runId,
  });

  const [selected, setSelected] = useState<TestCase | null>(null);
  // Reset the selected suite whenever the run or its report changes.
  useEffect(() => {
    setSelected(report.data?.test_cases?.[0] ?? null);
  }, [report.data, runId]);

  return (
    <div className="stagger space-y-6">
      <PageHeader
        eyebrow="Generated artifacts"
        title="Tests & Flows"
        subtitle="The user-flows the agent discovered and the Playwright suites it generated."
        action={<RunSwitcher runs={finishedRuns} value={runId} onChange={setRunId} />}
      />

      {finishedRuns.length === 0 && (
        <div className="card text-center text-[13px] text-faint">
          No finished runs yet — start one to generate tests.
        </div>
      )}

      {report.error && (
        <div className="card border-bad/40 text-[13px] text-bad">
          Could not load this run&apos;s report — {(report.error as Error).message}
        </div>
      )}

      {report.data && (
        <>
          {/* Flows */}
          <section className="card">
            <div className="panel-head">
              <h2 className="flex items-center gap-2 text-sm font-medium tracking-tight">
                <GitBranch className="h-4 w-4 text-accent" /> Flows
              </h2>
              <span className="eyebrow">{report.data.flows.length} discovered</span>
            </div>
            <div className="grid gap-2.5 md:grid-cols-2">
              {report.data.flows.map((f) => (
                <div key={f.id} className="rounded-lg border border-line bg-elevated/40 p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[13px] font-medium">{f.name}</span>
                    <span className={cn("badge font-mono", PRIORITY[f.priority] ?? PRIORITY.low)}>
                      {f.priority}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-muted">{f.description}</p>
                  {f.steps.length > 0 && (
                    <ol className="mt-2.5 space-y-1 border-l border-line-soft pl-3">
                      {f.steps.map((st, i) => (
                        <li key={i} className="text-[11px] text-faint">
                          <span className="text-muted">{st.action ?? "step"}</span> — {st.description}
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Test suites + code */}
          <section className="grid gap-3 lg:grid-cols-5">
            <div className="card lg:col-span-2">
              <div className="panel-head">
                <h2 className="flex items-center gap-2 text-sm font-medium tracking-tight">
                  <FileCode2 className="h-4 w-4 text-accent" /> Suites
                </h2>
                <span className="eyebrow">{report.data.test_cases.length}</span>
              </div>
              <div className="space-y-1">
                {report.data.test_cases.map((tc) => (
                  <button
                    key={tc.id}
                    onClick={() => setSelected(tc)}
                    className={cn(
                      "w-full rounded-lg px-3 py-2 text-left transition-colors",
                      selected?.id === tc.id ? "bg-elevated" : "hover:bg-elevated/50"
                    )}
                  >
                    <div className="truncate text-[13px] text-ink">{tc.name}</div>
                    <div className="mt-0.5 truncate font-mono text-[10px] text-faint">
                      {tc.file_path.split(/[/\\]/).pop()}
                    </div>
                  </button>
                ))}
                {report.data.test_cases.length === 0 && (
                  <p className="px-3 py-6 text-center text-[13px] text-faint">No tests generated.</p>
                )}
              </div>
            </div>

            <div className="card lg:col-span-3">
              <div className="panel-head">
                <h2 className="truncate text-sm font-medium tracking-tight">
                  {selected?.name ?? "Select a suite"}
                </h2>
                {selected && (
                  <span className="font-mono text-[10px] text-faint">{selected.file_path.split(/[/\\]/).pop()}</span>
                )}
              </div>
              {selected ? (
                <pre className="code max-h-[28rem]">{selected.playwright_code || "// (no code stored)"}</pre>
              ) : (
                <div className="rounded-lg border border-dashed border-line py-10 text-center text-[13px] text-faint">
                  Pick a suite to view its Playwright code.
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function RunSwitcher({
  runs,
  value,
  onChange,
}: {
  runs: { id: string; url: string; created_at: string | null }[];
  value: string | null;
  onChange: (id: string) => void;
}) {
  if (runs.length === 0) return null;
  return (
    <div className="relative">
      <select
        className="input min-w-[16rem] cursor-pointer appearance-none pr-9 font-mono text-xs"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
      >
        {runs.map((r) => (
          <option key={r.id} value={r.id}>
            {r.url} · {fmtDate(r.created_at)}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
    </div>
  );
}
