"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Plus } from "lucide-react";
import Link from "next/link";

import { HealingBars, PassRateTrend } from "@/components/Charts";
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/utils";

export default function DashboardPage() {
  const summary = useQuery({ queryKey: ["summary"], queryFn: api.summary });
  const trend = useQuery({ queryKey: ["trend"], queryFn: api.trend });
  const healing = useQuery({ queryKey: ["healing"], queryFn: api.healing });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.listRuns, refetchInterval: 5000 });

  const s = summary.data;

  return (
    <div className="stagger space-y-6">
      <PageHeader
        eyebrow="Mission control"
        title="Dashboard"
        subtitle="Pass rate, healing, and recent runs at a glance."
        action={
          <Link href="/runs/new" className="btn">
            <Plus className="h-4 w-4" /> New run
          </Link>
        }
      />

      {summary.error && (
        <div className="card border-bad/40 text-[13px] text-bad">
          Could not reach the API — {(summary.error as Error).message}
        </div>
      )}

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Total runs" value={s?.total_runs ?? "—"} />
        <StatCard
          label="Pass rate"
          value={s ? `${Math.round(s.overall_pass_rate)}%` : "—"}
          hint={s ? `${s.tests_passed}/${s.tests_total} tests passed` : undefined}
          accent
        />
        <StatCard label="Tests run" value={s?.tests_total ?? "—"} />
        <StatCard label="Selectors healed" value={s?.successful_heals ?? "—"} />
      </section>

      {/* Analytics, folded in: trend + healing side by side */}
      <section className="grid gap-3 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="panel-head">
            <h2 className="text-sm font-medium tracking-tight">Pass rate trend</h2>
            <span className="eyebrow">last {trend.data?.length ?? 0} runs</span>
          </div>
          {trend.data && trend.data.length > 0 ? (
            <PassRateTrend data={trend.data} />
          ) : (
            <EmptyHint>Run a few tests to chart your trend.</EmptyHint>
          )}
        </div>
        <div className="card">
          <div className="panel-head">
            <h2 className="text-sm font-medium tracking-tight">Healing outcomes</h2>
          </div>
          <HealingBars data={healing.data ?? {}} />
        </div>
      </section>

      <section className="card">
        <div className="panel-head">
          <h2 className="text-sm font-medium tracking-tight">Recent runs</h2>
          <Link href="/runs" className="inline-flex items-center gap-1 text-[11px] text-muted transition-colors hover:text-accent">
            View all <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </div>
        <div className="divide-y divide-line-soft">
          {(runs.data ?? []).slice(0, 6).map((r) => (
            <Link
              key={r.id}
              href={`/runs/${r.id}`}
              className="group -mx-2 flex items-center justify-between rounded-lg px-2 py-2.5 transition-colors hover:bg-elevated/50"
            >
              <div className="min-w-0">
                <div className="truncate text-[13px] text-ink">{r.url}</div>
                <div className="mt-0.5 font-mono text-[10px] text-faint">
                  {r.id} · {fmtDate(r.created_at)}
                </div>
              </div>
              <div className="flex items-center gap-4">
                <span className="font-mono text-[11px] text-muted tnum">
                  {r.passed}/{r.total}
                </span>
                <StatusBadge status={r.status} />
              </div>
            </Link>
          ))}
          {runs.data && runs.data.length === 0 && <EmptyHint>No runs yet — start your first one.</EmptyHint>}
        </div>
      </section>
    </div>
  );
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line py-8 text-center text-[13px] text-faint">
      {children}
    </div>
  );
}
