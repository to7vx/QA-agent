export interface ProviderInfo {
  id: string;
  label: string;
  models: string[];
  default_model: string;
  configured: boolean;
  masked_key: string | null;
}

export interface FlowStep {
  description: string;
  selector?: string | null;
  action?: string | null;
  expected_result?: string | null;
}

export interface Flow {
  id: string;
  name: string;
  description: string;
  url: string;
  priority: "high" | "medium" | "low";
  steps: FlowStep[];
  tags: string[];
}

export interface HealingAttempt {
  test_case_id: string;
  test_case_name: string;
  original_selector: string;
  new_selector: string | null;
  confidence: number;
  reasoning: string;
  outcome: string;
}

export interface TestResult {
  test_case_id: string;
  test_case_name: string;
  status: "pending" | "running" | "passed" | "failed" | "skipped" | "error";
  duration_ms: number;
  error_message: string | null;
  screenshot_path: string | null;
  healed: boolean;
  healing: HealingAttempt | null;
}

export interface RunEvent {
  type: string;
  data: Record<string, any>;
  timestamp: string;
}

export interface RunSummary {
  run_id: string;
  url: string;
  started_at: string | null;
  finished_at: string | null;
  provider: string;
  model: string;
  cancelled: boolean;
  total: number;
  passed: number;
  failed: number;
  healed: number;
  pass_rate: number;
  status: string | null;
}

export interface RunReport {
  meta: { run_id: string; provider: string; model: string; cancelled: boolean };
  report: {
    id: string;
    url: string;
    started_at: string;
    finished_at: string | null;
    flows: Flow[];
    results: TestResult[];
    healing_attempts: HealingAttempt[];
    markdown_path: string;
  } | null;
  status: string;
}

export interface AppSettings {
  defaults: { provider: string; model: string };
  providers: Record<string, { configured: boolean; masked_key: string | null }>;
}

export interface LibraryTest {
  id: string;
  name: string;
  description: string;
  scenario: string;
  url: string;
  file_path: string;
  origin: string;
  provider: string;
  model: string;
  tags: string[];
  created_at: string;
  code?: string;
}

export interface InsightsData {
  kpis: {
    runs: number;
    tests_run: number;
    pass_rate: number;
    healed: number;
    sites: number;
  };
  trend: {
    run_id: string;
    url: string;
    date: string | null;
    pass_rate: number;
    total: number;
  }[];
  flakiest: { name: string; fails: number; runs: number }[];
  healing: { healed: number; refused: number; failed: number; error: number };
}
