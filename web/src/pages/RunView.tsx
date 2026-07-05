import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { FileText, OctagonX, RotateCcw } from "lucide-react";
import { cancelRun, getRun, getRunTestCode, rerunFailed, useRunEvents } from "../api";
import type { RunReport } from "../types";
import FlowCard from "../components/FlowCard";
import PassRing from "../components/PassRing";
import PipelineStepper from "../components/PipelineStepper";
import StatusBadge from "../components/StatusBadge";
import TestTable from "../components/TestTable";

export default function RunView() {
  const { runId } = useParams<{ runId: string }>();
  if (!runId) return null;
  return <LiveRun key={runId} runId={runId} />;
}

function LiveRun({ runId }: { runId: string }) {
  const navigate = useNavigate();
  const run = useRunEvents(runId);
  const [report, setReport] = useState<RunReport | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [rerunError, setRerunError] = useState<string | null>(null);

  // Once finished, fetch the persisted report for extras (markdown path, etc.)
  useEffect(() => {
    if (run.finished) {
      getRun(runId).then(setReport).catch(() => {});
    }
  }, [run.finished, runId]);

  const rows = useMemo(() => {
    const ids = run.tests.map((t) => t.id);
    // include results whose test_generated event predates this session's stream
    for (const id of Object.keys(run.results)) {
      if (!ids.includes(id)) ids.push(id);
    }
    return ids.map((id) => ({
      id,
      name:
        run.tests.find((t) => t.id === id)?.name ??
        run.results[id]?.test_case_name ??
        id,
      result: run.results[id] ?? null,
      running: run.runningTestId === id,
    }));
  }, [run.tests, run.results, run.runningTestId]);

  const status = run.error
    ? "error"
    : run.cancelled
      ? "cancelled"
      : run.finished
        ? "finished"
        : "running";

  const doCancel = async () => {
    setCancelling(true);
    try {
      await cancelRun(runId);
    } catch {
      setCancelling(false);
    }
  };

  const doRerunFailed = async () => {
    setRerunError(null);
    try {
      const { run_id } = await rerunFailed(runId);
      navigate(`/runs/${run_id}`);
    } catch (err) {
      setRerunError((err as Error).message);
    }
  };

  const failedCount = run.summary?.failed ?? 0;

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="truncate font-mono text-lg">{run.url || "…"}</h1>
            <StatusBadge status={status} />
          </div>
          <div className="mt-1 font-mono text-[11px] text-dim">
            {run.provider && `${run.provider} · ${run.model} · `}run {runId}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {run.summary && <PassRing passRate={run.summary.pass_rate} />}
          {run.finished && !run.error && failedCount > 0 && (
            <button
              onClick={doRerunFailed}
              className="flex items-center gap-1.5 rounded-md border border-amber/50 px-3 py-1.5 text-xs text-amber transition-colors hover:bg-amber/10"
            >
              <RotateCcw size={13} />
              Re-run failed ({failedCount})
            </button>
          )}
          {status === "running" && (
            <button
              onClick={doCancel}
              disabled={cancelling}
              className="flex items-center gap-1.5 rounded-md border border-edge px-3 py-1.5 text-xs text-mut transition-colors hover:border-fail/50 hover:text-fail disabled:opacity-40"
            >
              <OctagonX size={13} />
              {cancelling ? "stopping…" : "stop run"}
            </button>
          )}
        </div>
      </div>

      {/* Pipeline conveyor */}
      <div className="mt-8 rounded-lg border border-edge bg-panel px-6 py-5">
        <PipelineStepper active={run.stage} done={run.stagesDone} failed={!!run.error} />
      </div>

      {run.error && (
        <div className="mt-4 rounded-lg border border-fail/30 bg-fail/5 px-4 py-3 text-sm text-fail">
          Run failed: {run.error}
        </div>
      )}
      {rerunError && (
        <div className="mt-4 rounded-lg border border-fail/30 bg-fail/5 px-4 py-3 text-xs text-fail">
          {rerunError}
        </div>
      )}
      {run.cancelled && !run.error && (
        <div className="mt-4 rounded-lg border border-edge bg-panel px-4 py-3 text-sm text-mut">
          Run stopped. Results up to that point are kept below.
        </div>
      )}

      {/* Summary strip */}
      {run.summary && (
        <div className="mt-4 grid grid-cols-3 gap-3">
          <Stat label="passed" value={run.summary.passed} tone="text-pass" />
          <Stat label="failed" value={run.summary.failed} tone="text-fail" />
          <Stat
            label="healed"
            value={run.healing.filter((h) => h.outcome === "healed").length}
            tone="text-heal"
          />
        </div>
      )}

      {/* Tests */}
      <section className="mt-8">
        <h2 className="font-display text-xs font-medium uppercase tracking-widest text-dim">
          Tests
        </h2>
        <div className="mt-3 overflow-hidden rounded-lg border border-edge bg-panel">
          <TestTable
            rows={rows}
            loadCode={(testId) =>
              getRunTestCode(runId, testId).then((r) => r.code)
            }
          />
        </div>
      </section>

      {/* Flows */}
      {run.flows.length > 0 && (
        <section className="mt-8">
          <h2 className="font-display text-xs font-medium uppercase tracking-widest text-dim">
            Flows discovered · {run.flows.length}
          </h2>
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            {run.flows.map((flow) => (
              <FlowCard key={flow.id} flow={flow} />
            ))}
          </div>
        </section>
      )}

      {/* Report link */}
      {report?.report?.markdown_path && (
        <div className="mt-8 flex items-center gap-2 rounded-lg border border-edge bg-panel px-4 py-3 text-xs text-mut">
          <FileText size={14} className="text-amber" />
          Markdown report saved to
          <code className="font-mono text-[11px] text-fg">
            {report.report.markdown_path}
          </code>
        </div>
      )}

      <div className="mt-10">
        <Link to="/" className="text-xs text-mut underline-offset-2 hover:text-fg hover:underline">
          ← start another run
        </Link>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg border border-edge bg-panel px-4 py-3">
      <div className={`font-display text-2xl font-bold ${tone}`}>{value}</div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-dim">{label}</div>
    </div>
  );
}
