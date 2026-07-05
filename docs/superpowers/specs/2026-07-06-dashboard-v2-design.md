# qa-agent Dashboard v2 — Design

**Date:** 2026-07-06
**Status:** Approved (Supabase dropped by user decision — free-tier limit; SQLite local store instead)

## Summary

v2 turns the dashboard from a run-viewer into a QA control center: a real local
database (SQLite), an AI Test Composer + test library ("Test Lab"), an Insights
page with trends, re-run-failed and code viewing on runs, proper model
dropdowns everywhere, and a fixed, restructured Settings page.

## Decisions

| Question | Decision |
|---|---|
| Database | **SQLite** at `<report_dir>/qa.db` (stdlib `sqlite3`, WAL). Supabase rejected: free-tier 2-project limit; user chose local. |
| What's stored | Runs (summary + full report JSON), per-test results (for flakiness queries), test-case library. Provider keys stay in the keystore. |
| Settings bugs | Test-connection unreliable (tiny token budget + no timeout), default-model editing clunky (free text, saved per keystroke), page bare. All fixed. |
| Model input | Dropdown of catalog models per provider + "Custom…" reveal for free text. Same component on New Run and Settings. |
| New features | AI Test Composer + library (Test Lab page), Insights page, re-run failed, test code viewer. |

## Architecture changes

```
src/qa_agent/
├── store.py            NEW — SQLite store: runs, test_results, test_cases
├── composer.py         NEW — plain-English scenario + URL → Playwright test
├── prompts.py          CHANGED — add COMPOSER_SYSTEM / COMPOSER_PROMPT
├── explorer.py         CHANGED — expose capture_snapshot(url, headless) helper
├── agent.py            CHANGED — run_tests() execute-only path; persist via store
├── dashboard/
│   ├── run_manager.py  CHANGED — store-backed history/reports; execute-only runs;
│   │                    rerun-failed; legacy report.json import on startup
│   └── api.py          CHANGED — new endpoints; test-connection fix
web/                    CHANGED — Test Lab, Insights, ModelSelect, Settings redesign,
                         RunView rerun/code, richer Home, nav update
```

### store.py

`Store(db_path)` — one class, `sqlite3` with `check_same_thread=False` + a
`threading.Lock` (single-writer local app). Tables:

- `runs(id TEXT PK, url, provider, model, started_at, finished_at, status,
  cancelled INT, total INT, passed INT, failed INT, healed INT, pass_rate REAL,
  markdown_path, report_json TEXT)`
- `test_results(run_id, test_case_id, name, status, duration_ms REAL,
  healed INT, error)` — one row per executed test, for flakiness/trend queries
- `test_cases(id TEXT PK, name, description, scenario, url, file_path, code,
  origin TEXT, provider, model, tags_json, created_at)` — the library;
  `origin` ∈ `composed`

API: `save_run(report_payload)`, `list_runs()`, `get_run(run_id)`,
`insights()` (aggregates below), `add_test_case(...)`, `list_test_cases()`,
`get_test_case(id)`, `delete_test_case(id)`, `import_legacy(report_dir)`
(one-time scan of `reports/*/report.json` for pre-v2 runs not in the DB).

### Execute-only runs

`QAAgent.run_tests(test_cases, heal, cancel, run_id, url_label)` — skips
explore/generate; emits the same event stream (stage goes straight to
`execute`); produces and persists a normal `Report`. Used by:

- `POST /api/tests/{id}/run` — run one library test
- `POST /api/runs/{run_id}/rerun-failed` — re-run only the failed/error tests
  of a finished run (test files resolved from the stored report + manifest;
  missing files → 409 with explanation)

`RunParams` gains `mode: "full" | "execute"` and `test_ids: list[str]`;
the run manager builds the `TestCase` list for execute mode.

### Composer (composer.py)

`compose(provider, url, scenario, settings) -> TestCase`:
1. Capture page snapshot (reuse explorer's capture via new public
   `capture_snapshot(url, headless)` helper) — best-effort; on failure compose
   without page context.
2. `provider.complete(COMPOSER_SYSTEM, COMPOSER_PROMPT.format(...))` → code.
3. Strip fences + `ast.parse` check; one repair attempt (reuse generator
   helpers).
4. Write `generated_tests/composed_<slug>_<id>.py`, append to manifest,
   insert into `test_cases` table.

`POST /api/compose {url, scenario, provider, model}` → `{test_case}` (incl.
code). Runs synchronously in a worker thread (30–90s); the UI shows progress.

### New/changed endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/insights` | `{kpis: {runs, tests_run, pass_rate, healed, sites}, trend: [{date, pass_rate, total}], flakiest: [{name, fails, runs}], healing: {healed, refused, failed}}` |
| `GET /api/tests` | Library list (no code) |
| `GET /api/tests/{id}` | One test incl. code |
| `DELETE /api/tests/{id}` | Remove from library (+ delete file) |
| `POST /api/tests/{id}/run` | Execute-only run → `{run_id}` |
| `POST /api/compose` | Create a test from plain English |
| `POST /api/runs/{id}/rerun-failed` | Execute-only run of failures → `{run_id}` |
| `GET /api/runs/{id}/code/{test_case_id}` | Source of a generated test (path-safe: resolved under output_dir only) |
| `POST /api/settings/keys/{p}/test` | FIXED: 64-token budget, 20s thread timeout, empty-but-no-error counts as OK |

### Frontend

- **ModelSelect** component: `<select>` of catalog models + "Custom…" option
  revealing a mono text input. Used in New Run + Settings.
- **Settings**: three sections — Providers (key cards, fixed test button),
  Defaults (provider + ModelSelect), Data (DB path, run/test counts, note that
  keys never leave the machine).
- **Test Lab** (`/lab`): top — composer form (URL, scenario textarea, provider/
  model, "Compose test"); below — library table (name, origin, target, created,
  actions: Run ▸, view/copy code, delete). Composing shows a progress state;
  result appears with code preview + Run button.
- **Insights** (`/insights`): KPI cards; pass-rate area chart (hand-rolled SVG,
  last 30 runs); flakiest tests bar list; healing outcome donut. Empty state
  invites a first run.
- **RunView**: "Re-run failed (N)" button when finished with failures; per-row
  "view code" expands the Playwright source (fetched lazily).
- **Home**: stats strip (runs, avg pass rate, healed) + two feature cards
  (Test Lab, Insights) between hero and recent runs.
- Nav: New run · Test Lab · Insights · History · Settings.

### Error handling

- Store failures never break a run (best-effort writes, log to server console).
- Composer failures return 422 with the model's error or syntax message.
- Rerun-failed with no failed tests or missing files → 409 with message.
- Code endpoint rejects any path outside `output_dir` (404).
- Legacy import is idempotent (INSERT OR IGNORE by run id).

### Testing

- `tests/test_store.py` — CRUD, insights aggregates, legacy import (tmp dirs).
- `tests/test_composer.py` — fake provider returns code / broken code / garbage.
- `tests/test_execute_only.py` — run_tests event sequence + rerun-failed flow.
- `tests/test_api.py` — extended: insights, tests CRUD, compose (fake), rerun.
- Frontend: `tsc && vite build` clean.

## Out of scope

Cloud sync (revisit when user upgrades Supabase), auth, scheduled runs,
multi-page crawling.
