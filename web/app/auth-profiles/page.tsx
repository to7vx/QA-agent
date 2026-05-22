"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Terminal, Trash2, Upload } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PageHeader } from "@/components/PageHeader";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/utils";

export default function AuthProfilesPage() {
  const qc = useQueryClient();
  const profiles = useQuery({ queryKey: ["auth-profiles"], queryFn: api.authProfiles.list });

  const [name, setName] = useState("");
  const [origin, setOrigin] = useState("");
  const [json, setJson] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => {
      let storage_state: Record<string, unknown>;
      try {
        storage_state = JSON.parse(json);
      } catch {
        throw new Error("storage_state must be valid JSON.");
      }
      return api.authProfiles.create({ name, origin, storage_state });
    },
    onSuccess: () => {
      setName("");
      setOrigin("");
      setJson("");
      setParseError(null);
      qc.invalidateQueries({ queryKey: ["auth-profiles"] });
    },
    onError: (e) => setParseError((e as Error).message),
  });

  const [pendingDelete, setPendingDelete] = useState<{ id: string; name: string } | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) => api.authProfiles.delete(id),
    onSuccess: () => {
      setPendingDelete(null);
      qc.invalidateQueries({ queryKey: ["auth-profiles"] });
    },
  });

  return (
    <div className="stagger space-y-6">
      <PageHeader
        eyebrow="Authenticated testing"
        title="Auth Profiles"
        subtitle="Stored login sessions the agent injects to test pages behind a sign-in."
      />

      {/* CLI capture hint */}
      <div className="card flex items-start gap-3">
        <Terminal className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
        <div className="min-w-0 text-[13px] text-muted">
          Capturing a live login needs a real browser, so do it from the CLI — then it appears here:
          <pre className="code mt-2 whitespace-pre-wrap text-[12px]">qa-agent auth capture https://app.example.com/login --name &quot;staging&quot;</pre>
          Or paste an exported Playwright <span className="font-mono text-faint">storage_state</span> JSON below.
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-5">
        {/* List */}
        <section className="card lg:col-span-3">
          <div className="panel-head">
            <h2 className="flex items-center gap-2 text-sm font-medium tracking-tight">
              <ShieldCheck className="h-4 w-4 text-accent" /> Saved sessions
            </h2>
            <span className="eyebrow">{profiles.data?.length ?? 0}</span>
          </div>
          <div className="divide-y divide-line-soft">
            {(profiles.data ?? []).map((p) => (
              <div key={p.id} className="flex items-center justify-between py-3">
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-ink">{p.name}</div>
                  <div className="mt-0.5 truncate font-mono text-[10px] text-faint">
                    {p.origin || "any origin"} · {fmtDate(p.created_at)}
                  </div>
                </div>
                <button
                  onClick={() => setPendingDelete({ id: p.id, name: p.name })}
                  className="rounded-lg border border-line p-2 text-faint transition-colors hover:border-bad/40 hover:text-bad"
                  aria-label={`Delete ${p.name}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
            {profiles.data && profiles.data.length === 0 && (
              <div className="rounded-lg border border-dashed border-line py-8 text-center text-[13px] text-faint">
                No saved sessions yet.
              </div>
            )}
          </div>
        </section>

        {/* Import form */}
        <section className="card lg:col-span-2">
          <div className="panel-head">
            <h2 className="flex items-center gap-2 text-sm font-medium tracking-tight">
              <Upload className="h-4 w-4 text-accent" /> Import session
            </h2>
          </div>
          <form
            className="space-y-3.5"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <div>
              <label className="label">Name</label>
              <input className="input" placeholder="staging" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div>
              <label className="label">Origin</label>
              <input
                className="input font-mono"
                placeholder="https://app.example.com"
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
              />
            </div>
            <div>
              <label className="label">storage_state JSON</label>
              <textarea
                className="input min-h-[8rem] font-mono text-[11px]"
                placeholder='{"cookies": [...], "origins": [...]}'
                value={json}
                onChange={(e) => setJson(e.target.value)}
                required
              />
            </div>
            {parseError && <p className="text-[13px] text-bad">{parseError}</p>}
            {create.isSuccess && <p className="text-[13px] text-good">Saved.</p>}
            <button className="btn w-full" disabled={create.isPending || !name || !json}>
              {create.isPending ? "Saving…" : "Save session"}
            </button>
          </form>
        </section>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        destructive
        title="Delete this auth profile?"
        description={
          <>
            <span className="font-mono text-ink">{pendingDelete?.name}</span> will be permanently
            removed. Runs that inject this session will no longer be able to test pages behind its
            login.
          </>
        }
        confirmLabel="Delete profile"
        pending={remove.isPending}
        onConfirm={() => pendingDelete && remove.mutate(pendingDelete.id)}
        onCancel={() => !remove.isPending && setPendingDelete(null)}
      />
    </div>
  );
}
