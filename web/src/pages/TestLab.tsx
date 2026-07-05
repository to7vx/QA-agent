import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Beaker,
  ChevronDown,
  ChevronRight,
  Copy,
  Loader2,
  Play,
  Trash2,
} from "lucide-react";
import {
  composeTest,
  deleteTest,
  getProviders,
  getSettings,
  getTest,
  getTests,
  runTest,
} from "../api";
import type { LibraryTest, ProviderInfo } from "../types";
import ModelSelect from "../components/ModelSelect";

export default function TestLab() {
  const navigate = useNavigate();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [providerId, setProviderId] = useState("anthropic");
  const [model, setModel] = useState("");
  const [url, setUrl] = useState("");
  const [scenario, setScenario] = useState("");
  const [composing, setComposing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tests, setTests] = useState<LibraryTest[]>([]);
  const [justComposed, setJustComposed] = useState<LibraryTest | null>(null);

  const refresh = () => getTests().then((r) => setTests(r.tests)).catch(() => {});

  useEffect(() => {
    getProviders().then(setProviders).catch(() => {});
    getSettings()
      .then((s) => {
        setProviderId(s.defaults.provider);
        setModel(s.defaults.model);
      })
      .catch(() => {});
    refresh();
  }, []);

  const selected = providers.find((p) => p.id === providerId);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setJustComposed(null);
    setComposing(true);
    try {
      const target = url.match(/^https?:\/\//) ? url : `https://${url}`;
      const test = await composeTest({
        url: target,
        scenario,
        provider: providerId,
        model: model || selected?.default_model || "",
      });
      setJustComposed(test);
      setScenario("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setComposing(false);
    }
  };

  const startRun = async (id: string) => {
    try {
      const { run_id } = await runTest(id);
      navigate(`/runs/${run_id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const remove = async (id: string) => {
    await deleteTest(id).catch(() => {});
    if (justComposed?.id === id) setJustComposed(null);
    refresh();
  };

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <div className="flex items-center gap-3">
        <Beaker size={22} className="text-amber" />
        <h1 className="font-display text-2xl font-bold tracking-tight">Test Lab</h1>
      </div>
      <p className="mt-1 max-w-xl text-sm text-mut">
        Describe a test in plain English — the agent reads the real page, writes the
        Playwright code, and saves it to your library.
      </p>

      {/* Composer */}
      <form onSubmit={submit} className="mt-7 rounded-lg border border-edge bg-panel p-5">
        <div className="flex items-stretch overflow-hidden rounded-md border border-edge bg-raise focus-within:border-amber/60">
          <span className="flex items-center pl-3 font-mono text-xs text-dim">https://</span>
          <input
            value={url.replace(/^https?:\/\//, "")}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="the-page-to-test.com"
            required
            spellCheck={false}
            className="min-w-0 flex-1 bg-transparent px-1.5 py-2.5 font-mono text-xs text-fg placeholder:text-dim focus:outline-none"
          />
        </div>
        <textarea
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
          required
          minLength={10}
          rows={3}
          placeholder={
            "Describe the scenario like you'd brief a junior tester:\n" +
            '"Search for \'playwright\', open the first result, expect the page title to contain playwright."'
          }
          className="mt-3 w-full resize-y rounded-md border border-edge bg-raise px-3 py-2.5 text-sm leading-relaxed text-fg placeholder:text-dim focus:border-amber/60 focus:outline-none"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <select
            value={providerId}
            onChange={(e) => {
              setProviderId(e.target.value);
              const p = providers.find((x) => x.id === e.target.value);
              setModel(p?.default_model ?? "");
            }}
            aria-label="Provider"
            className="rounded-md border border-edge bg-raise px-2.5 py-1.5 text-xs text-fg focus:border-amber/60 focus:outline-none"
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id} disabled={!p.configured}>
                {p.label}
                {p.configured ? "" : " — no key"}
              </option>
            ))}
          </select>
          <ModelSelect provider={selected} value={model} onChange={setModel} />
          <button
            type="submit"
            disabled={composing || !url.trim() || scenario.trim().length < 10}
            className="ml-auto flex items-center gap-2 rounded-md bg-amber px-5 py-2 font-display text-xs font-semibold text-ink transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {composing ? (
              <>
                <Loader2 size={13} className="animate-spin" /> reading the page &
                writing the test…
              </>
            ) : (
              "Compose test"
            )}
          </button>
        </div>
        {error && (
          <p className="mt-3 rounded border border-fail/30 bg-fail/5 px-3 py-2 text-xs text-fail">
            {error}
          </p>
        )}
      </form>

      {/* Fresh result */}
      {justComposed && (
        <div className="mt-4 rounded-lg border border-pass/30 bg-pass/5 p-4">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-pass">
              Test composed: {justComposed.name}
            </span>
            <button
              onClick={() => startRun(justComposed.id)}
              className="ml-auto flex items-center gap-1.5 rounded-md bg-pass px-3.5 py-1.5 font-display text-xs font-semibold text-ink hover:opacity-90"
            >
              <Play size={12} /> Run it now
            </button>
          </div>
          <pre className="mt-3 max-h-64 overflow-auto rounded border border-edge bg-ink p-3 font-mono text-[11px] leading-relaxed text-fg/90">
            {justComposed.code}
          </pre>
        </div>
      )}

      {/* Library */}
      <section className="mt-10">
        <h2 className="font-display text-xs font-medium uppercase tracking-widest text-dim">
          Library · {tests.length} test{tests.length === 1 ? "" : "s"}
        </h2>
        {tests.length === 0 ? (
          <p className="mt-3 rounded-lg border border-edge bg-panel px-5 py-8 text-center text-xs text-dim">
            Composed tests land here. They also run as part of full suite runs.
          </p>
        ) : (
          <div className="mt-3 divide-y divide-edge/60 rounded-lg border border-edge bg-panel">
            {tests.map((test) => (
              <LibraryRow
                key={test.id}
                test={test}
                onRun={() => startRun(test.id)}
                onDelete={() => remove(test.id)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function LibraryRow({
  test,
  onRun,
  onDelete,
}: {
  test: LibraryTest;
  onRun: () => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && code === null) {
      const full = await getTest(test.id).catch(() => null);
      setCode(full?.code ?? "// source unavailable");
    }
  };

  const copy = async () => {
    if (!code) return;
    await navigator.clipboard.writeText(code).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div>
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          onClick={toggle}
          aria-label={open ? "Hide code" : "View code"}
          className="text-dim hover:text-fg"
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm">{test.name}</div>
          <div className="mt-0.5 truncate font-mono text-[10px] text-dim">
            {test.url} · {test.provider}/{test.model} ·{" "}
            {new Date(test.created_at + "Z").toLocaleDateString()}
          </div>
        </div>
        <button
          onClick={onRun}
          className="flex items-center gap-1.5 rounded-md border border-pass/40 px-3 py-1.5 text-[11px] text-pass transition-colors hover:bg-pass/10"
        >
          <Play size={11} /> Run
        </button>
        <button
          onClick={onDelete}
          aria-label={`Delete ${test.name}`}
          className="rounded-md border border-edge p-1.5 text-mut transition-colors hover:border-fail/50 hover:text-fail"
        >
          <Trash2 size={12} />
        </button>
      </div>
      {open && (
        <div className="relative bg-ink/50 px-11 pb-4">
          <button
            onClick={copy}
            className="absolute right-6 top-2 flex items-center gap-1 rounded border border-edge bg-panel px-2 py-1 text-[10px] text-mut hover:text-fg"
          >
            <Copy size={10} /> {copied ? "copied!" : "copy"}
          </button>
          <pre className="max-h-72 overflow-auto rounded border border-edge bg-ink p-3 font-mono text-[11px] leading-relaxed text-fg/90">
            {code ?? "loading…"}
          </pre>
        </div>
      )}
    </div>
  );
}
