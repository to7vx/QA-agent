"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Globe, Layers, Loader2, Play, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function NewRunPage() {
  const router = useRouter();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });

  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"single" | "crawl">("single");
  const [maxPages, setMaxPages] = useState(5);
  const [heal, setHeal] = useState(true);
  const [headless, setHeadless] = useState(true);

  const mutation = useMutation({
    mutationFn: () => api.createRun({ url, mode, max_pages: maxPages, heal, headless }),
    onSuccess: (res) => router.push(`/runs/${res.run_id}`),
  });

  const hasKey = settings.data?.has_anthropic_key || settings.data?.has_gemini_key;

  return (
    <div className="mx-auto max-w-2xl stagger space-y-6">
      <PageHeader
        eyebrow="Launch"
        title="New run"
        subtitle="Point the agent at a URL — it explores, generates tests, runs them, and self-heals."
      />

      {settings.data && !hasKey && (
        <div className="card flex items-center gap-3 border-warn/40 text-sm text-warn">
          <ShieldCheck className="h-4 w-4 shrink-0" />
          <span>
            No provider key on file. Add one on{" "}
            <a href="/settings" className="underline underline-offset-2">Settings</a> first.
          </span>
        </div>
      )}

      <form
        className="card space-y-7"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div>
          <label className="label">Target URL</label>
          <div className="relative">
            <Globe className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <input
              className="input pl-10 font-mono"
              placeholder="https://example.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
              autoFocus
            />
          </div>
        </div>

        <div>
          <label className="label">Mode</label>
          <div className="grid grid-cols-2 gap-2">
            <ModeTile
              active={mode === "single"}
              onClick={() => setMode("single")}
              icon={<Globe className="h-4 w-4" />}
              title="Single page"
              desc="Test one URL"
            />
            <ModeTile
              active={mode === "crawl"}
              onClick={() => setMode("crawl")}
              icon={<Layers className="h-4 w-4" />}
              title="Crawl"
              desc="Discover same-origin pages"
            />
          </div>
        </div>

        {mode === "crawl" && (
          <div className="animate-fade-up">
            <label className="label">Max pages</label>
            <input
              type="number"
              min={1}
              max={50}
              className="input font-mono tnum"
              value={maxPages}
              onChange={(e) => setMaxPages(Number(e.target.value))}
            />
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          <Toggle checked={heal} onChange={setHeal} label="Self-healing" />
          <Toggle checked={headless} onChange={setHeadless} label="Headless" />
        </div>

        {mutation.error && (
          <p className="rounded-xl border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">
            {(mutation.error as Error).message}
          </p>
        )}

        <button className="btn w-full" disabled={mutation.isPending || !url}>
          {mutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Starting…
            </>
          ) : (
            <>
              <Play className="h-4 w-4" /> Start run
            </>
          )}
        </button>
      </form>
    </div>
  );
}

function ModeTile({
  active,
  onClick,
  icon,
  title,
  desc,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col gap-1.5 rounded-xl border p-4 text-left transition-all duration-200",
        active
          ? "border-accent/50 bg-accent/5 shadow-glow"
          : "border-line bg-elevated/40 hover:border-line hover:bg-elevated"
      )}
    >
      <span className={cn("flex items-center gap-2 text-sm font-medium", active ? "text-accent" : "text-ink")}>
        {icon}
        {title}
      </span>
      <span className="text-xs text-muted">{desc}</span>
    </button>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "flex items-center gap-2.5 rounded-xl border px-3.5 py-2 text-sm transition-colors",
        checked ? "border-accent/40 bg-accent/5 text-ink" : "border-line bg-elevated/40 text-muted"
      )}
    >
      <span
        className={cn(
          "relative h-4 w-7 rounded-full transition-colors",
          checked ? "bg-accent" : "bg-line"
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-3 w-3 rounded-full bg-bg transition-all",
            checked ? "left-3.5" : "left-0.5"
          )}
        />
      </span>
      {label}
    </button>
  );
}
