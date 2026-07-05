# Dashboard v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SQLite-backed run/test storage, AI Test Composer + library (Test Lab), Insights page, re-run failed, code viewer, model dropdowns, fixed Settings.

**Architecture:** A `Store` class (stdlib sqlite3, WAL, lock) becomes the single persistence point, fed by the run manager; execute-only runs reuse the existing agent/executor/SSE machinery; the composer is a small module reusing the explorer's snapshot capture and the generator's syntax helpers.

**Tech Stack:** Python stdlib sqlite3, FastAPI, existing provider layer; React/Vite/Tailwind (hand-rolled SVG charts, no chart lib).

## Global Constraints

- DB file: `<report_dir>/qa.db`; store writes are best-effort — never fail a run.
- Provider keys never touch the DB or HTTP responses (masked only).
- Prompts only in `prompts.py`; inter-module data via `models.py` types.
- Code-view endpoint must resolve paths strictly under `settings.output_dir`.
- Frontend: after editing `web/`, `npm run build` into `dashboard/static/` and commit.
- All existing 71 tests keep passing.

---

### Task 1: Store (SQLite)

**Files:** Create `src/qa_agent/store.py`; Test `tests/test_store.py`

**Produces:**
```python
class Store:
    def __init__(self, db_path: Path)                     # creates schema
    def save_run(self, payload: dict) -> None             # payload = report.json shape {meta, report}
    def list_runs(self) -> list[dict]                     # history summaries (same keys as RunManager.history entries)
    def get_run(self, run_id: str) -> dict | None         # full payload
    def insights(self) -> dict                            # {kpis, trend, flakiest, healing}
    def add_test_case(self, tc: dict) -> None             # keys: id,name,description,scenario,url,file_path,code,origin,provider,model,tags
    def list_test_cases(self) -> list[dict]               # without code
    def get_test_case(self, tc_id: str) -> dict | None    # with code
    def delete_test_case(self, tc_id: str) -> None
    def import_legacy(self, report_dir: Path) -> int      # idempotent, returns #imported
```
Schema per spec (`runs`, `test_results`, `test_cases`). `save_run` also inserts
one `test_results` row per result. TDD: tests cover save/list/get roundtrip,
insights aggregates over 3 fake runs, flakiest ordering, legacy import
idempotency, test-case CRUD.

### Task 2: Execute-only agent path

**Files:** Modify `src/qa_agent/agent.py` (add `run_tests`), `src/qa_agent/explorer.py` (public `async capture_snapshot(url, headless) -> PageSnapshot` wrapping the existing private logic); Test `tests/test_execute_only.py`

**Produces:**
```python
async QAAgent.run_tests(self, test_cases: list[TestCase], heal=True,
                        cancel=None, run_id=None, url_label="") -> Report
```
Event sequence: `run_started` (with `mode:"execute"`), `stage execute`,
`test_started`/`test_result` per test, `stage report`, `run_finished`.
Persists report.json exactly like `run()` (reuse `_finish`/`_persist`).

### Task 3: Composer

**Files:** Create `src/qa_agent/composer.py`; Modify `src/qa_agent/prompts.py` (add `COMPOSER_SYSTEM`, `COMPOSER_PROMPT` with `{url}`, `{scenario}`, `{page_context}` slots); Test `tests/test_composer.py`

**Produces:**
```python
def compose(provider: LLMProvider, url: str, scenario: str,
            settings: Settings, page_context: str = "") -> TestCase
# raises ComposerError on unusable output (syntax still broken after 1 repair)
async def compose_with_snapshot(provider, url, scenario, settings) -> TestCase
```
Reuses `generator._check_syntax`, `_strip_fences`, `_slugify` (import them).
Writes `generated_tests/composed_<slug>_<6hex>.py` + appends to
`manifest.json` (create manifest if absent). Tests: good code path, repair
path, garbage → ComposerError; snapshot failure falls back to no-context.

### Task 4: Run manager v2

**Files:** Modify `src/qa_agent/dashboard/run_manager.py`; Test extend `tests/test_run_manager.py`

- Constructor creates `self.store = Store(settings.report_dir / "qa.db")` and
  calls `store.import_legacy(settings.report_dir)` once.
- `RunParams` gains `mode: Literal["full","execute"] = "full"`,
  `test_ids: list[str] = []`, `url_label: str = ""`.
- Worker: `mode=="execute"` → build `TestCase` list from store/manifest and call
  `agent.run_tests(...)`; else `agent.run(...)` as today.
- On finish (any mode): `store.save_run(payload)` read from the freshly
  written report.json (best-effort try/except).
- `history()`/`get_report()` read store first, fall back to file scan.
- New: `rerun_failed(run_id) -> str` (collects failed/error results from the
  stored report, resolves file paths via manifest + `test_cases` table,
  raises `ValueError` when nothing to rerun / files missing) and
  `run_single_test(tc_id) -> str`.
- Agent factory signature stays `(settings, provider, emit)`; the returned
  object must now also expose `run_tests` (update FakeAgent in tests).

### Task 5: API v2

**Files:** Modify `src/qa_agent/dashboard/api.py`; Test extend `tests/test_api.py`

Endpoints per spec table: `/api/insights`, `/api/tests` (GET),
`/api/tests/{id}` (GET/DELETE), `/api/tests/{id}/run` (POST),
`/api/compose` (POST, body `{url, scenario, provider, model}`, runs
`compose_with_snapshot` via `asyncio.to_thread`… composer is async: call in
endpoint directly with `await`), `/api/runs/{id}/rerun-failed` (POST),
`/api/runs/{id}/code/{test_case_id}` (GET, path-safe).
Fix `/api/settings/keys/{p}/test`: `max_tokens=64`, run in thread with 20s
timeout (`concurrent.futures`), empty-string response without exception = ok.

### Task 6: Frontend v2

**Files:** Create `web/src/components/ModelSelect.tsx`, `web/src/pages/TestLab.tsx`, `web/src/pages/Insights.tsx`, `web/src/components/charts.tsx`; Modify `App.tsx` (nav: New run · Test Lab · Insights · History · Settings), `api.ts` (+types), `NewRun.tsx` (ModelSelect, stats strip, feature cards), `Settings.tsx` (3 sections, ModelSelect, Data card), `RunView.tsx` (re-run failed button, per-row view code).

Then `npm run build` (tsc must pass), commit bundle.

### Task 7: Integration

- Full pytest suite green; live server smoke: insights, tests, compose(400 w/o key), SPA routes `/lab`, `/insights`.
- Update CLAUDE.md architecture/status + README features.
- Merge per finishing-a-development-branch.

## Self-Review

- Spec coverage: store T1, execute-only T2, composer T3, manager T4, API T5, all UI T6, docs/verify T7. Settings fix in T5+T6. Model dropdown T6. ✓
- Interfaces consistent: `Store` methods used by T4/T5 match T1; `run_tests` used by T4 matches T2; `compose_with_snapshot` used by T5 matches T3. ✓
