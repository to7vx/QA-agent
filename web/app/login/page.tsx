"use client";

import { FlaskConical, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient, supabaseConfigured } from "@/lib/supabase/client";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!supabaseConfigured) {
    return (
      <Shell>
        <h1 className="text-xl font-semibold tracking-tight">Auth not configured</h1>
        <p className="mt-2 text-sm text-muted">
          Supabase env vars aren&apos;t set. The dashboard is running in local (no-auth) mode — head to the{" "}
          <a href="/" className="text-accent underline underline-offset-2">overview</a>.
        </p>
      </Shell>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setBusy(true);
    const supabase = createClient();
    try {
      if (mode === "signup") {
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        setInfo("Check your email to confirm, then sign in.");
        setMode("signin");
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        router.push("/");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function oauth(provider: "google" | "github") {
    const supabase = createClient();
    await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: `${window.location.origin}/` },
    });
  }

  return (
    <Shell>
      <div className="mb-7 flex items-center gap-3">
        <span className="relative grid h-10 w-10 place-items-center rounded-xl border border-line bg-elevated">
          <FlaskConical className="h-5 w-5 text-accent" />
          <span className="absolute inset-0 rounded-xl shadow-glow" />
        </span>
        <div>
          <div className="text-lg font-semibold tracking-tight">QA Agent</div>
          <div className="eyebrow mt-0.5">{mode === "signin" ? "welcome back" : "create account"}</div>
        </div>
      </div>

      <form className="space-y-4" onSubmit={submit}>
        <div>
          <label className="label">Email</label>
          <input className="input font-mono" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <label className="label">Password</label>
          <input
            className="input font-mono"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error && <p className="text-sm text-bad">{error}</p>}
        {info && <p className="text-sm text-good">{info}</p>}
        <button className="btn w-full" disabled={busy}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {mode === "signin" ? "Sign in" : "Sign up"}
        </button>
      </form>

      <div className="my-5 flex items-center gap-3 text-faint">
        <span className="h-px flex-1 bg-line" />
        <span className="font-mono text-[11px] uppercase tracking-wider">or</span>
        <span className="h-px flex-1 bg-line" />
      </div>

      <div className="flex gap-3">
        <button className="btn-ghost flex-1" onClick={() => oauth("google")}>Google</button>
        <button className="btn-ghost flex-1" onClick={() => oauth("github")}>GitHub</button>
      </div>

      <button
        className="mt-5 text-sm text-muted transition-colors hover:text-accent"
        onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
      >
        {mode === "signin" ? "Need an account? Sign up" : "Have an account? Sign in"}
      </button>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh place-items-center px-6">
      <div className="card w-full max-w-md animate-fade-up p-8">{children}</div>
    </div>
  );
}
