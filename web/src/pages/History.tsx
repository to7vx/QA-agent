import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { getRuns } from "../api";
import type { RunSummary } from "../types";
import PassRing from "../components/PassRing";
import StatusBadge from "../components/StatusBadge";

export default function HistoryPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [query, setQuery] = useState("");
  const [onlyFailed, setOnlyFailed] = useState(false);

  useEffect(() => {
    getRuns().then((r) => setRuns(r.runs)).catch(() => {});
  }, []);

  const filtered = useMemo(
    () =>
      runs.filter(
        (run) =>
          run.url.toLowerCase().includes(query.toLowerCase()) &&
          (!onlyFailed || run.failed > 0),
      ),
    [runs, query, onlyFailed],
  );

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <h1 className="font-display text-2xl font-bold tracking-tight">History</h1>

      <div className="mt-5 flex items-center gap-4">
        <div className="flex flex-1 items-center gap-2 rounded-md border border-edge bg-panel px-3">
          <Search size={14} className="text-dim" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by URL"
            className="w-full bg-transparent py-2 font-mono text-xs text-fg placeholder:text-dim focus:outline-none"
          />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-mut">
          <input
            type="checkbox"
            checked={onlyFailed}
            onChange={(e) => setOnlyFailed(e.target.checked)}
            className="accent-[var(--color-fail)]"
          />
          with failures
        </label>
      </div>

      {filtered.length === 0 ? (
        <div className="mt-10 rounded-lg border border-edge bg-panel px-6 py-12 text-center">
          <p className="text-sm text-mut">
            {runs.length === 0
              ? "No runs yet. Start one from New run."
              : "Nothing matches that filter."}
          </p>
          {runs.length === 0 && (
            <Link
              to="/"
              className="mt-3 inline-block rounded-md bg-amber px-4 py-2 font-display text-xs font-semibold text-ink"
            >
              Run your first test
            </Link>
          )}
        </div>
      ) : (
        <div className="mt-5 divide-y divide-edge/60 rounded-lg border border-edge bg-panel">
          {filtered.map((run) => (
            <Link
              key={run.run_id}
              to={`/runs/${run.run_id}`}
              className="flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-raise/40"
            >
              <PassRing passRate={run.pass_rate} size={40} label={false} />
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-xs">{run.url}</div>
                <div className="mt-0.5 text-[11px] text-dim">
                  {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                  {" · "}
                  {run.provider} / {run.model}
                </div>
              </div>
              <div className="shrink-0 text-right font-mono text-[11px] text-mut">
                <span className="text-pass">{run.passed}✓</span>{" "}
                <span className={run.failed > 0 ? "text-fail" : "text-dim"}>
                  {run.failed}✗
                </span>
                {run.healed > 0 && <span className="text-heal"> {run.healed}⚡</span>}
              </div>
              <StatusBadge status={run.status ?? "finished"} />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
