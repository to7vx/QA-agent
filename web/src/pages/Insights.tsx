import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getInsights } from "../api";
import type { InsightsData } from "../types";
import { BarList, HealingDonut, TrendChart } from "../components/charts";

export default function InsightsPage() {
  const [data, setData] = useState<InsightsData | null>(null);

  useEffect(() => {
    getInsights().then(setData).catch(() => {});
  }, []);

  if (!data) return null;

  if (data.kpis.runs === 0) {
    return (
      <div className="mx-auto max-w-4xl px-8 py-10">
        <h1 className="font-display text-2xl font-bold tracking-tight">Insights</h1>
        <div className="mt-10 rounded-lg border border-edge bg-panel px-6 py-14 text-center">
          <p className="text-sm text-mut">
            Insights build up as you run tests — there's nothing to chart yet.
          </p>
          <Link
            to="/"
            className="mt-4 inline-block rounded-md bg-amber px-4 py-2 font-display text-xs font-semibold text-ink"
          >
            Start your first run
          </Link>
        </div>
      </div>
    );
  }

  const kpis = [
    { label: "runs", value: data.kpis.runs },
    { label: "tests executed", value: data.kpis.tests_run },
    { label: "avg pass rate", value: `${Math.round(data.kpis.pass_rate)}%` },
    { label: "selectors healed", value: data.kpis.healed },
    { label: "sites tested", value: data.kpis.sites },
  ];

  const maxFails = Math.max(...data.flakiest.map((f) => f.fails), 1);

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <h1 className="font-display text-2xl font-bold tracking-tight">Insights</h1>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-lg border border-edge bg-panel px-4 py-3">
            <div className="font-display text-xl font-bold">{kpi.value}</div>
            <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-dim">
              {kpi.label}
            </div>
          </div>
        ))}
      </div>

      <section className="mt-8 rounded-lg border border-edge bg-panel p-5">
        <h2 className="font-display text-xs font-medium uppercase tracking-widest text-dim">
          Pass rate per run
        </h2>
        <div className="mt-4">
          <TrendChart points={data.trend} />
        </div>
      </section>

      <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
        <section className="rounded-lg border border-edge bg-panel p-5">
          <h2 className="font-display text-xs font-medium uppercase tracking-widest text-dim">
            Flakiest tests
          </h2>
          <div className="mt-4">
            {data.flakiest.length === 0 ? (
              <p className="text-xs text-dim">No failing tests recorded — clean sheet.</p>
            ) : (
              <BarList
                items={data.flakiest.map((f) => ({
                  label: f.name,
                  value: f.fails,
                  max: maxFails,
                  hint: `${f.fails}/${f.runs} runs failed`,
                }))}
              />
            )}
          </div>
        </section>

        <section className="rounded-lg border border-edge bg-panel p-5">
          <h2 className="font-display text-xs font-medium uppercase tracking-widest text-dim">
            Self-healing outcomes
          </h2>
          <div className="mt-4">
            <HealingDonut healing={data.healing} />
          </div>
        </section>
      </div>
    </div>
  );
}
