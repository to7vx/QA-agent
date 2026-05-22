// Mirrors qa_agent.api.schemas. Kept in sync by hand (or regenerate with
// openapi-typescript against the running API's /openapi.json).

export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface RunSummary {
  id: string;
  url: string;
  status: RunStatus;
  mode: string;
  model: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  error: string | null;
}

export interface RunAccepted {
  run_id: string;
  status: string;
}

export interface RunRequest {
  url: string;
  model?: string | null;
  headless?: boolean;
  heal?: boolean;
  mode?: string;
  max_pages?: number;
  auth_profile_id?: string | null;
}

export interface AnalyticsSummary {
  total_runs: number;
  tests_total: number;
  tests_passed: number;
  tests_failed: number;
  overall_pass_rate: number;
  successful_heals: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}

export interface TrendPoint {
  run_id: string;
  url: string;
  created_at: string | null;
  pass_rate: number;
  total: number;
  passed: number;
  failed: number;
}

export interface UserSettings {
  default_model: string;
  has_anthropic_key: boolean;
  has_gemini_key: boolean;
  updated_at: string | null;
}

export interface ProgressEvent {
  seq: number;
  ts?: string | null;
  phase: string;
  status: string;
  message: string;
  data: Record<string, unknown>;
}

export interface FlowStep {
  description: string;
  selector: string | null;
  action: string | null;
  expected_result: string | null;
}

export interface Flow {
  id: string;
  name: string;
  description: string;
  url: string;
  priority: string;
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
  timestamp: string;
}

export interface TestResult {
  test_case_id: string;
  test_case_name: string;
  status: string;
  duration_ms: number;
  error_message: string | null;
  screenshot_path: string | null;
  metadata: Record<string, unknown>;
  healed: boolean;
  healing: HealingAttempt | null;
}

export interface TestCase {
  id: string;
  flow_id: string;
  name: string;
  description: string;
  playwright_code: string;
  file_path: string;
  tags: string[];
}

export interface Report {
  id: string;
  url: string;
  started_at: string | null;
  finished_at: string | null;
  flows: Flow[];
  test_cases: TestCase[];
  results: TestResult[];
  healing_attempts: HealingAttempt[];
  markdown_path: string;
}

export interface AuthProfileSummary {
  id: string;
  name: string;
  origin: string;
  created_at: string | null;
  expires_at: string | null;
}
