"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/utils";

export default function RunsPage() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.listRuns, refetchInterval: 5000 });

  return (
    <div className="stagger space-y-6">
      <PageHeader
        eyebrow="History"
        title="Runs"
        subtitle="Every test run, newest first."
        action={
          <Link href="/runs/new" className="btn">
            <Plus className="h-4 w-4" /> New run
          </Link>
        }
      />

      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left">
              {["Target", "Run", "Result", "Pass", "Created", "Status"].map((h) => (
                <th key={h} className="px-5 py-3 eyebrow font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line-soft">
            {(runs.data ?? []).map((r) => (
              <tr key={r.id} className="group transition-colors hover:bg-elevated/50">
                <td className="max-w-[280px] truncate px-5 py-3.5">
                  <Link href={`/runs/${r.id}`} className="text-ink transition-colors group-hover:text-accent">
                    {r.url}
                  </Link>
                </td>
                <td className="px-5 py-3.5 font-mono text-[11px] text-faint">{r.id}</td>
                <td className="px-5 py-3.5 font-mono text-muted tnum">
                  {r.passed}/{r.total}
                </td>
                <td className="px-5 py-3.5">
                  <PassPill rate={r.pass_rate} status={r.status} />
                </td>
                <td className="px-5 py-3.5 text-muted">{fmtDate(r.created_at)}</td>
                <td className="px-5 py-3.5">
                  <StatusBadge status={r.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {runs.data && runs.data.length === 0 && (
          <p className="px-5 py-10 text-center text-sm text-faint">No runs yet — start one.</p>
        )}
      </div>
    </div>
  );
}

function PassPill({ rate, status }: { rate: number; status: string }) {
  if (status !== "succeeded" && status !== "failed") {
    return <span className="font-mono text-xs text-faint">—</span>;
  }
  const pct = Math.round(rate);
  const color = pct >= 80 ? "text-good" : pct >= 50 ? "text-warn" : "text-bad";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-elevated">
        <div className="h-full rounded-full bg-accent/80" style={{ width: `${pct}%` }} />
      </div>
      <span className={`font-mono text-xs tnum ${color}`}>{pct}%</span>
    </div>
  );
}
