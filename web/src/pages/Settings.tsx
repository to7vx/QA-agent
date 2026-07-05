import { useEffect, useState } from "react";
import { CheckCircle2, KeyRound, Loader2, Trash2, XCircle } from "lucide-react";
import {
  deleteKey,
  getProviders,
  getSettings,
  putDefaults,
  putKey,
  testKey,
} from "../api";
import type { ProviderInfo } from "../types";

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [defaults, setDefaults] = useState({ provider: "anthropic", model: "" });

  const refresh = () => {
    getProviders().then(setProviders).catch(() => {});
    getSettings().then((s) => setDefaults(s.defaults)).catch(() => {});
  };
  useEffect(refresh, []);

  const saveDefaults = async (provider: string, model: string) => {
    setDefaults({ provider, model });
    try {
      await putDefaults(provider, model);
    } catch {
      /* transient; next load re-syncs */
    }
  };

  const defaultProvider = providers.find((p) => p.id === defaults.provider);

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <h1 className="font-display text-2xl font-bold tracking-tight">Settings</h1>
      <p className="mt-1 text-sm text-mut">
        Keys are stored on this machine only, in{" "}
        <code className="font-mono text-xs">~/.qa-agent/config.json</code>. They never
        leave it except to call the provider you choose.
      </p>

      <section className="mt-8 space-y-4">
        {providers.map((p) => (
          <KeyCard key={p.id} provider={p} onChange={refresh} />
        ))}
      </section>

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
            className="rounded-md border border-edge bg-raise px-2.5 py-1.5 text-xs text-fg focus:border-amber/60 focus:outline-none"
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <input
            value={defaults.model}
            onChange={(e) => saveDefaults(defaults.provider, e.target.value)}
            list="default-model-suggestions"
            spellCheck={false}
            className="w-56 rounded-md border border-edge bg-raise px-2.5 py-1.5 font-mono text-xs text-fg focus:border-amber/60 focus:outline-none"
          />
          <datalist id="default-model-suggestions">
            {defaultProvider?.models.map((m) => <option key={m} value={m} />)}
          </datalist>
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
