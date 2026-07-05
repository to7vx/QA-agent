import { useEffect, useMemo, useReducer } from "react";
import type {
  AppSettings,
  Flow,
  HealingAttempt,
  InsightsData,
  LibraryTest,
  ProviderInfo,
  RunEvent,
  RunReport,
  RunSummary,
  TestResult,
} from "./types";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const getProviders = () => api<ProviderInfo[]>("/api/providers");
export const getSettings = () => api<AppSettings>("/api/settings");
export const putKey = (provider: string, apiKey: string) =>
  api<{ configured: boolean; masked_key: string }>(`/api/settings/keys/${provider}`, {
    method: "PUT",
    body: JSON.stringify({ api_key: apiKey }),
  });
export const deleteKey = (provider: string) =>
  api<{ configured: boolean }>(`/api/settings/keys/${provider}`, { method: "DELETE" });
export const testKey = (provider: string) =>
  api<{ ok: boolean; error?: string }>(`/api/settings/keys/${provider}/test`, {
    method: "POST",
  });
export const putDefaults = (provider: string, model: string) =>
  api(`/api/settings/defaults`, {
    method: "PUT",
    body: JSON.stringify({ provider, model }),
  });
export const startRun = (params: {
  url: string;
  provider: string;
  model: string;
  headed: boolean;
  heal: boolean;
}) => api<{ run_id: string }>("/api/runs", { method: "POST", body: JSON.stringify(params) });
export const getRuns = () =>
  api<{ runs: RunSummary[]; active: RunSummary | null }>("/api/runs");
export const getRun = (runId: string) => api<RunReport>(`/api/runs/${runId}`);
export const cancelRun = (runId: string) =>
  api(`/api/runs/${runId}/cancel`, { method: "POST" });
export const rerunFailed = (runId: string) =>
  api<{ run_id: string }>(`/api/runs/${runId}/rerun-failed`, { method: "POST" });
export const getRunTestCode = (runId: string, testCaseId: string) =>
  api<{ code: string; file_path: string }>(`/api/runs/${runId}/code/${testCaseId}`);
export const getInsights = () => api<InsightsData>("/api/insights");
export const getTests = () => api<{ tests: LibraryTest[] }>("/api/tests");
export const getTest = (id: string) => api<LibraryTest>(`/api/tests/${id}`);
export const deleteTest = (id: string) =>
  api(`/api/tests/${id}`, { method: "DELETE" });
export const runTest = (id: string) =>
  api<{ run_id: string }>(`/api/tests/${id}/run`, { method: "POST" });
export const composeTest = (body: {
  url: string;
  scenario: string;
  provider: string;
  model: string;
}) => api<LibraryTest>("/api/compose", { method: "POST", body: JSON.stringify(body) });

// ---------------------------------------------------------------------------
// Live run state, folded from the SSE event stream
// ---------------------------------------------------------------------------

export interface RunState {
  runId: string;
  url: string;
  provider: string;
  model: string;
  stage: string | null; // explore | generate | execute | report
  stagesDone: string[];
  flows: Flow[];
  tests: { id: string; name: string }[];
  runningTestId: string | null;
  results: Record<string, TestResult>;
  healing: HealingAttempt[];
  finished: boolean;
  cancelled: boolean;
  error: string | null;
  summary: { total: number; passed: number; failed: number; pass_rate: number } | null;
}

const initialRunState = (runId: string): RunState => ({
  runId,
  url: "",
  provider: "",
  model: "",
  stage: null,
  stagesDone: [],
  flows: [],
  tests: [],
  runningTestId: null,
  results: {},
  healing: [],
  finished: false,
  cancelled: false,
  error: null,
  summary: null,
});

function reduce(state: RunState, event: RunEvent): RunState {
  const d = event.data;
  switch (event.type) {
    case "run_started":
      return { ...state, url: d.url, provider: d.provider, model: d.model };
    case "stage": {
      const done = state.stage ? [...state.stagesDone, state.stage] : state.stagesDone;
      return { ...state, stage: d.stage, stagesDone: done };
    }
    case "flows_found":
      return { ...state, flows: d.flows };
    case "test_generated":
      return { ...state, tests: [...state.tests, { id: d.test.id, name: d.test.name }] };
    case "test_started":
      return { ...state, runningTestId: d.test_id };
    case "test_result":
      return {
        ...state,
        runningTestId: null,
        results: { ...state.results, [d.result.test_case_id]: d.result },
      };
    case "healing":
      return { ...state, healing: [...state.healing, d.attempt] };
    case "cancelled":
      return { ...state, cancelled: true };
    case "run_error":
      return { ...state, error: d.message, finished: true };
    case "run_finished": {
      const done = state.stage ? [...state.stagesDone, state.stage] : state.stagesDone;
      return {
        ...state,
        stage: null,
        stagesDone: done,
        finished: true,
        cancelled: d.cancelled,
        summary: {
          total: d.total,
          passed: d.passed,
          failed: d.failed,
          pass_rate: d.pass_rate,
        },
      };
    }
    default:
      return state;
  }
}

/** Subscribe to a run's SSE stream; replays history, then follows live. */
export function useRunEvents(runId: string): RunState {
  const [state, dispatch] = useReducer(reduce, runId, initialRunState);

  useEffect(() => {
    const source = new EventSource(`/api/runs/${runId}/events`);
    source.onmessage = (msg) => {
      try {
        dispatch(JSON.parse(msg.data));
      } catch {
        /* ignore malformed lines */
      }
    };
    source.addEventListener("done", () => source.close());
    return () => source.close();
  }, [runId]);

  return useMemo(() => state, [state]);
}
