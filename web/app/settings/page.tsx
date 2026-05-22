"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Cpu, Gauge, KeyRound, Loader2, User } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const MODELS = [
  "anthropic/claude-sonnet-4-6",
  "anthropic/claude-haiku-4-5-20251001",
  "gemini/gemini-2.5-flash",
  "gemini/gemini-1.5-flash",
];

const TABS = [
  { id: "providers", label: "Providers", icon: KeyRound },
  { id: "model", label: "Model", icon: Cpu },
  { id: "usage", label: "Usage", icon: Gauge },
  { id: "account", label: "Account", icon: User },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function SettingsPage() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const summary = useQuery({ queryKey: ["summary"], queryFn: api.summary });
  const [tab, setTab] = useState<TabId>("providers");

  const [anthropic, setAnthropic] = useState("");
  const [gemini, setGemini] = useState("");
  const [model, setModel] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (body: { anthropic_key?: string; gemini_key?: string; default_model?: string }) =>
      api.updateSettings(body),
    onSuccess: () => {
      setAnthropic("");
      setGemini("");
      setModel(null);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const d = settings.data;

  return (
    <div className="mx-auto max-w-3xl stagger space-y-6">
      <PageHeader eyebrow="Configuration" title="Settings" subtitle="Keys, model, usage and account." />

      {/* Tabs */}
      <div className="flex gap-1 rounded-xl border border-line bg-surface/60 p-1">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn("tab flex flex-1 items-center justify-center gap-2", tab === id && "tab-active")}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {tab === "providers" && (
        <form
          className="card space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({ anthropic_key: anthropic || undefined, gemini_key: gemini || undefined });
          }}
        >
          <KeyField
            label="Anthropic API key"
            set={d?.has_anthropic_key}
            placeholder={d?.has_anthropic_key ? "•••••••• (leave blank to keep)" : "sk-ant-…"}
            value={anthropic}
            onChange={setAnthropic}
          />
          <KeyField
            label="Gemini API key"
            set={d?.has_gemini_key}
            placeholder={d?.has_gemini_key ? "•••••••• (leave blank to keep)" : "AIza…"}
            value={gemini}
            onChange={setGemini}
          />
          <SaveButton pending={save.isPending} ok={save.isSuccess} error={save.error as Error | null} />
        </form>
      )}

      {tab === "model" && (
        <form
          className="card space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({ default_model: model ?? d?.default_model ?? MODELS[0] });
          }}
        >
          <div>
            <label className="label">Default model</label>
            <select
              className="input font-mono"
              value={model ?? d?.default_model ?? MODELS[0]}
              onChange={(e) => setModel(e.target.value)}
            >
              {MODELS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-muted">
              Used when a run doesn&apos;t specify a model. The matching provider key must be set.
            </p>
          </div>
          <SaveButton pending={save.isPending} ok={save.isSuccess} error={save.error as Error | null} />
        </form>
      )}

      {tab === "usage" && (
        <section className="space-y-3">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Total runs" value={summary.data?.total_runs ?? "—"} />
            <StatCard label="Tests run" value={summary.data?.tests_total ?? "—"} />
            <StatCard
              label="Pass rate"
              value={summary.data ? `${Math.round(summary.data.overall_pass_rate)}%` : "—"}
              accent
            />
            <StatCard label="Heals" value={summary.data?.successful_heals ?? "—"} />
          </div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard
              label="LLM cost (est.)"
              value={summary.data ? `$${summary.data.cost_usd.toFixed(4)}` : "—"}
              accent
            />
            <StatCard label="Tokens in" value={summary.data?.tokens_in.toLocaleString() ?? "—"} />
            <StatCard label="Tokens out" value={summary.data?.tokens_out.toLocaleString() ?? "—"} />
            <StatCard
              label="Avg cost / run"
              value={
                summary.data && summary.data.total_runs
                  ? `$${(summary.data.cost_usd / summary.data.total_runs).toFixed(4)}`
                  : "—"
              }
            />
          </div>
          <div className="card text-[13px] text-muted">
            Cost is an estimate from per-model token pricing (display only, not billing). Per-user
            quotas are enforced server-side: concurrent runs and a daily cap. Adjust them via the API
            env vars <span className="font-mono text-faint">QA_AGENT_MAX_CONCURRENT_RUNS</span> and{" "}
            <span className="font-mono text-faint">QA_AGENT_DAILY_RUN_CAP</span>.
          </div>
        </section>
      )}

      {tab === "account" && (
        <div className="card space-y-3 text-[13px] text-muted">
          <Row label="Mode" value={<span className="font-mono text-ink">local · no-auth</span>} />
          <Row label="Default model" value={<span className="font-mono text-ink">{d?.default_model ?? "—"}</span>} />
          <Row
            label="Keys configured"
            value={
              <span className="font-mono text-ink">
                {[d?.has_anthropic_key && "anthropic", d?.has_gemini_key && "gemini"].filter(Boolean).join(", ") || "none"}
              </span>
            }
          />
          <p className="pt-1 text-xs text-faint">
            Sign-in accounts appear here when the dashboard runs against Supabase auth.
          </p>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-line-soft py-2 last:border-0">
      <span className="text-muted">{label}</span>
      {value}
    </div>
  );
}

function SaveButton({ pending, ok, error }: { pending: boolean; ok: boolean; error: Error | null }) {
  return (
    <div className="space-y-2">
      {error && <p className="text-[13px] text-bad">{error.message}</p>}
      {ok && (
        <p className="flex items-center gap-2 text-[13px] text-good">
          <CheckCircle2 className="h-4 w-4" /> Saved.
        </p>
      )}
      <button className="btn w-full" disabled={pending}>
        {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
        {pending ? "Saving…" : "Save"}
      </button>
    </div>
  );
}

function KeyField({
  label,
  set,
  placeholder,
  value,
  onChange,
}: {
  label: string;
  set?: boolean;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="label flex items-center gap-2">
        {label}
        {set && (
          <span className="badge border-good/25 bg-good/10 text-good">
            <span className="h-1.5 w-1.5 rounded-full bg-good" /> set
          </span>
        )}
      </label>
      <input
        className="input font-mono"
        type="password"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete="off"
      />
    </div>
  );
}
