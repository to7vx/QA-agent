"use client";

import { createClient, supabaseConfigured } from "@/lib/supabase/client";
import type {
  AnalyticsSummary,
  AuthProfileSummary,
  Report,
  RunAccepted,
  RunRequest,
  RunSummary,
  TrendPoint,
  UserSettings,
} from "@/lib/types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function authHeader(): Promise<Record<string, string>> {
  if (!supabaseConfigured) return {};
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token
    ? { Authorization: `Bearer ${session.access_token}` }
    : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeader()),
    ...(init?.headers ?? {}),
  };
  const resp = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

async function requestVoid(path: string, init?: RequestInit): Promise<void> {
  const headers = { ...(await authHeader()), ...(init?.headers ?? {}) };
  const resp = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* no body (e.g. 204/404) */
    }
    throw new Error(detail);
  }
}

export const api = {
  listRuns: () => request<RunSummary[]>("/runs"),
  getRun: (id: string) => request<RunSummary>(`/runs/${id}`),
  getReport: (id: string) => request<Report>(`/runs/${id}/report`),
  createRun: (body: RunRequest) =>
    request<RunAccepted>("/runs", { method: "POST", body: JSON.stringify(body) }),
  summary: () => request<AnalyticsSummary>("/analytics/summary"),
  trend: () => request<TrendPoint[]>("/analytics/pass-rate-trend"),
  healing: () => request<Record<string, number>>("/analytics/healing"),
  getSettings: () => request<UserSettings>("/settings"),
  updateSettings: (body: Partial<UserSettings> & { anthropic_key?: string; gemini_key?: string }) =>
    request<UserSettings>("/settings", { method: "PUT", body: JSON.stringify(body) }),
  authProfiles: {
    list: () => request<AuthProfileSummary[]>("/auth-profiles"),
    create: (body: { name: string; origin: string; storage_state: Record<string, unknown> }) =>
      request<{ id: string; name: string; origin: string }>("/auth-profiles", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    delete: (id: string) => requestVoid(`/auth-profiles/${id}`, { method: "DELETE" }),
  },
};

// SSE URL with the access token as a query param (EventSource can't set headers).
export async function eventsUrl(runId: string): Promise<string> {
  const base = `${API_URL}/runs/${runId}/events`;
  if (!supabaseConfigured) return base;
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token
    ? `${base}?access_token=${encodeURIComponent(session.access_token)}`
    : base;
}
