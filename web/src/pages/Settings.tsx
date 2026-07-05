import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Database,
  KeyRound,
  Loader2,
  Trash2,
  XCircle,
} from "lucide-react";
import {
  deleteKey,
  getInsights,
  getProviders,
  getSettings,
  putDefaults,
  putKey,
  testKey,
} from "../api";
import type { InsightsData, ProviderInfo } from "../types";
import ModelSelect from "../components/ModelSelect";

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [defaults, setDefaults] = useState({ provider: "anthropic", model: "" });
  const [insights, setInsights] = useState<InsightsData | null>(null);
  const [defaultsSaved, setDefaultsSaved] = useState(false);

  const refresh = () => {
    getProviders().then(setProviders).catch(() => {});
    getSettings().then((s) => setDefaults(s.defaults)).catch(() => {});
    getInsights().then(setInsights).catch(() => {});
  };
  useEffect(refresh, []);

  const saveDefaults = async (provider: string, model: string) => {
    setDefaults({ provider, model });
    setDefaultsSaved(false);
    try {
      await putDefaults(provider, model);
      setDefaultsSaved(true);
      setTimeout(() => setDefaultsSaved(false), 2000);
    } catch {
      /* transient; next load re-syncs */
    }
  };

  const defaultProvider = providers.find((p) => p.id === defaults.provider);

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <h1 className="font-display text-2xl font-bold tracking-tight">Settings</h1>

      {/* 1 — Providers */}
      <section className="mt-8">
        <h2 className="font-display text-xs font-medium uppercase tracking-widest text-dim">
          Providers
        </h2>
        <p className="mt-1.5 text-xs leading-relaxed text-mut">
          Add a key for each AI you want to test with. Keys are stored on this
          machine only (<code className="font-mono">~/.qa-agent/config.json</code>) and
          never leave it except to call the provider you choose.
        </p>
        <div className="mt-3 space-y-3">
          {providers.map((p) => (
            <KeyCard key={p.id} provider={p} onChange={refresh} />
          ))}
        </div>
      </section>

      {/* 2 — Defaults */}
      <section className="mt-10">
        <h2 className="font-display text-xs font-medium uppercase tracking-widest text-dim">
          Defaults for new runs
        </h2>
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-edge bg-panel px-4 py-3.5">
          <select
            value={defaults.provider}
            onChange={(e) => {
              const p = providers.find((x) => x.id === e.target.value);
              saveDefaults(e.target.value, p?.default_model ?? "");
            }}
            aria-label="Default provider"
            className="rounded-md border border-edge bg-raise px-2.5 py-1.5 text-xs text-fg focus:border-amber/60 focus:outline-none"
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <ModelSelect
            provider={defaultProvider}
            value={defaults.model}
            onChange={(m) => saveDefaults(defaults.provider, m)}
          />
          {defaultsSaved && (
            <span className="flex items-center gap-1 text-[11px] text-pass">
              <CheckCircle2 size={12} /> saved
            </span>
          )}
        </div>
      </section>

      {/* 3 — Data */}
      <section className="mt-10">
        <h2 className="font-display text-xs font-medium uppercase tracking-widest text-dim">
          Data
        </h2>
        <div className="mt-3 flex items-start gap-3 rounded-lg border border-edge bg-panel px-4 py-3.5">
          <Database size={15} className="mt-0.5 shrink-0 text-amber" />
          <div className="text-xs leading-relaxed text-mut">
            Runs and your test library live in a local SQLite database at{" "}
            <code className="font-mono text-fg">reports/qa.db</code>
            {insights && (
              <>
                {" — currently "}
                <span className="text-fg">{insights.kpis.runs}</span> runs and{" "}
                <span className="text-fg">{insights.kpis.tests_run}</span> executed
                tests
              </>
            )}
            . Markdown reports and screenshots sit alongside it in{" "}
            <code className="font-mono text-fg">reports/</code>. Nothing is sent to
            any cloud.
          </div>
        </div>
      </section>
    </div>
  );
}

function KeyCard({ provider, onChange }: { provider: ProviderInfo; onChange: () => void }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; error?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    setTest(null);
    try {
      await putKey(provider.id, value);
      setValue("");
      onChange();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setTest(null);
    try {
      await deleteKey(provider.id);
      onChange();
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    setBusy(true);
    setTest(null);
    try {
      setTest(await testKey(provider.id));
    } catch (err) {
      setTest({ ok: false, error: (err as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <div className="flex items-center gap-2.5">
        <KeyRound size={15} className={provider.configured ? "text-pass" : "text-dim"} />
        <h3 className="font-display text-sm font-semibold">{provider.label}</h3>
        {provider.configured && (
          <span className="font-mono text-[11px] text-dim">{provider.masked_key}</span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {provider.configured && (
            <>
              <button
                onClick={runTest}
                disabled={busy}
                className="rounded-md border border-edge px-2.5 py-1 text-[11px] text-mut transition-colors hover:text-fg disabled:opacity-40"
              >
                {busy ? <Loader2 size={12} className="animate-spin" /> : "Test connection"}
              </button>
              <button
                onClick={remove}
                disabled={busy}
                aria-label={`Remove ${provider.label} key`}
                className="rounded-md border border-edge p-1.5 text-mut transition-colors hover:border-fail/50 hover:text-fail disabled:opacity-40"
              >
                <Trash2 size={12} />
              </button>
            </>
          )}
        </div>
      </div>

      <div className="mt-3 flex gap-2">
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={provider.configured ? "Replace key" : "Paste API key"}
          spellCheck={false}
          className="min-w-0 flex-1 rounded-md border border-edge bg-raise px-3 py-2 font-mono text-xs text-fg placeholder:text-dim focus:border-amber/60 focus:outline-none"
        />
        <button
          onClick={save}
          disabled={busy || !value.trim()}
          className="rounded-md bg-amber px-4 font-display text-xs font-semibold text-ink transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          Save key
        </button>
      </div>

      {error && <p className="mt-2 text-xs text-fail">{error}</p>}
      {test && (
        <p
          className={`mt-2 flex items-center gap-1.5 text-xs ${
            test.ok ? "text-pass" : "text-fail"
          }`}
        >
          {test.ok ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
          {test.ok ? "Key works — provider responded." : `Key check failed: ${test.error}`}
        </p>
      )}
    </div>
  );
}
