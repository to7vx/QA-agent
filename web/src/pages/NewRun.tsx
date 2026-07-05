import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Beaker,
  ChartNoAxesColumn,
  KeyRound,
  Loader2,
} from "lucide-react";
import { getInsights, getProviders, getRuns, getSettings, startRun } from "../api";
import type { InsightsData, ProviderInfo, RunSummary } from "../types";
import ModelSelect from "../components/ModelSelect";
import PassRing from "../components/PassRing";
import StatusBadge from "../components/StatusBadge";

export default function NewRun() {
  const navigate = useNavigate();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [recent, setRecent] = useState<RunSummary[]>([]);
  const [active, setActive] = useState<RunSummary | null>(null);
  const [insights, setInsights] = useState<InsightsData | null>(null);

  const [url, setUrl] = useState("");
  const [providerId, setProviderId] = useState("anthropic");
  const [model, setModel] = useState("");
  const [headed, setHeaded] = useState(false);
  const [heal, setHeal] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProviders().then(setProviders).catch(() => {});
    getSettings()
      .then((s) => {
        setProviderId(s.defaults.provider);
        setModel(s.defaults.model);
      })
      .catch(() => {});
    getRuns()
      .then((r) => {
        setRecent(r.runs.slice(0, 5));
        setActive(r.active);
      })
      .catch(() => {});
    getInsights().then(setInsights).catch(() => {});
  }, []);

  const selected = providers.find((p) => p.id === providerId);
  const anyConfigured = providers.some((p) => p.configured);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const target = url.match(/^https?:\/\//) ? url : `https://${url}`;
      const { run_id } = await startRun({
        url: target,
        provider: providerId,
        model: model || selected?.default_model || "",
        headed,
        heal,
      });
      navigate(`/runs/${run_id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-8 py-14">
      <h1 className="font-display text-3xl font-bold tracking-tight">
        Point it at a page.
      </h1>
      <p className="mt-2 max-w-lg text-sm leading-relaxed text-mut">
        The agent explores the page, writes Playwright tests, runs them, and
        heals broken selectors — you watch it happen.
      </p>

      {providers.length > 0 && !anyConfigured && (
        <Link
          to="/settings"
          className="mt-6 flex items-center gap-3 rounded-lg border border-amber/40 bg-amber/5 px-4 py-3 text-sm text-amber transition-colors hover:bg-amber/10"
        >
          <KeyRound size={16} />
          No API key yet — add one in Settings to run your first test.
          <ArrowRight size={14} className="ml-auto" />
        </Link>
      )}

      {active && (
        <Link
          to={`/runs/${active.run_id}`}
          className="mt-6 flex items-center gap-3 rounded-lg border border-edge bg-panel px-4 py-3 text-sm transition-colors hover:bg-raise"
        >
          <span className="h-2 w-2 animate-pulse rounded-full bg-amber" />
          A run is in progress on <span className="font-mono text-xs">{active.url}</span>
          <ArrowRight size={14} className="ml-auto text-mut" />
        </Link>
      )}

      <form onSubmit={submit} className="mt-8">
        {/* Command bar — the product in one line */}
        <div className="flex items-stretch overflow-hidden rounded-lg border border-edge bg-panel focus-within:border-amber/60">
          <span className="flex items-center pl-4 font-mono text-sm text-dim">
            https://
          </span>
          <input
            value={url.replace(/^https?:\/\//, "")}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="the-page-you-want-tested.com"
            required
            autoFocus
            spellCheck={false}
            className="min-w-0 flex-1 bg-transparent px-1.5 py-3.5 font-mono text-sm text-fg placeholder:text-dim focus:outline-none"
          />
          <button
            type="submit"
            disabled={busy || !url.trim()}
            className="m-1.5 flex items-center gap-2 rounded-md bg-amber px-5 font-display text-sm font-semibold text-ink transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : "Run tests"}
          </button>
        </div>

        {error && (
          <p className="mt-3 rounded border border-fail/30 bg-fail/5 px-3 py-2 text-xs text-fail">
            {error}
          </p>
        )}

        {/* Provider + model + toggles */}
        <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex overflow-hidden rounded-md border border-edge">
            {providers.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  setProviderId(p.id);
                  setModel(p.default_model);
                }}
                className={`px-3 py-1.5 text-xs transition-colors ${
                  providerId === p.id
                    ? "bg-raise font-medium text-fg"
                    : "bg-panel text-mut hover:text-fg"
                }`}
                title={p.configured ? "key configured" : "no key configured"}
              >
                {p.label.split(" ")[0]}
                <span
                  className={`ml-1.5 inline-block h-1.5 w-1.5 rounded-full ${
                    p.configured ? "bg-pass" : "bg-dim"
                  }`}
                />
              </button>
            ))}
          </div>

          <ModelSelect provider={selected} value={model} onChange={setModel} />

          <label className="flex cursor-pointer items-center gap-2 text-xs text-mut">
            <input
              type="checkbox"
              checked={heal}
              onChange={(e) => setHeal(e.target.checked)}
              className="accent-[var(--color-heal)]"
            />
            self-healing
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-mut">
            <input
              type="checkbox"
              checked={headed}
              onChange={(e) => setHeaded(e.target.checked)}
              className="accent-[var(--color-amber)]"
            />
            show browser
          </label>
        </div>
      </form>

      {/* Quick stats + feature cards */}
      {insights && insights.kpis.runs > 0 && (
        <div className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-2 rounded-lg border border-edge bg-panel px-5 py-3.5 font-mono text-[11px] text-mut">
          <span>
            <span className="text-fg">{insights.kpis.runs}</span> runs
          </span>
          <span>
            <span className="text-fg">{insights.kpis.tests_run}</span> tests executed
          </span>
          <span>
            <span className={insights.kpis.pass_rate >= 80 ? "text-pass" : "text-amber"}>
              {Math.round(insights.kpis.pass_rate)}%
            </span>{" "}
            avg pass rate
          </span>
          {insights.kpis.healed > 0 && (
            <span>
              <span className="text-heal">{insights.kpis.healed}</span> selectors healed
            </span>
          )}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Link
          to="/lab"
          className="group rounded-lg border border-edge bg-panel p-4 transition-colors hover:border-amber/40"
        >
          <div className="flex items-center gap-2.5">
            <Beaker size={16} className="text-amber" />
            <span className="font-display text-sm font-semibold">Test Lab</span>
            <ArrowRight size={13} className="ml-auto text-dim transition-transform group-hover:translate-x-0.5" />
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-mut">
            Write a test in plain English — the agent turns it into runnable
            Playwright code and keeps it in your library.
          </p>
        </Link>
        <Link
          to="/insights"
          className="group rounded-lg border border-edge bg-panel p-4 transition-colors hover:border-amber/40"
        >
          <div className="flex items-center gap-2.5">
            <ChartNoAxesColumn size={16} className="text-heal" />
            <span className="font-display text-sm font-semibold">Insights</span>
            <ArrowRight size={13} className="ml-auto text-dim transition-transform group-hover:translate-x-0.5" />
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-mut">
            Pass-rate trends, flakiest tests, and healing stats across every run.
          </p>
        </Link>
      </div>

      {/* Recent runs */}
      {recent.length > 0 && (
        <section className="mt-14">
          <h2 className="font-display text-xs font-medium uppercase tracking-widest text-dim">
            Recent runs
          </h2>
          <div className="mt-3 divide-y divide-edge/60 rounded-lg border border-edge bg-panel">
            {recent.map((run) => (
              <Link
                key={run.run_id}
                to={`/runs/${run.run_id}`}
                className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-raise/40"
              >
                <PassRing passRate={run.pass_rate} size={34} label={false} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-xs">{run.url}</div>
                  <div className="mt-0.5 text-[11px] text-dim">
                    {run.passed}/{run.total} passed
                    {run.healed > 0 && ` · ${run.healed} healed`}
                    {" · "}
                    {run.provider}
                  </div>
                </div>
                <StatusBadge status={run.status ?? "finished"} />
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
