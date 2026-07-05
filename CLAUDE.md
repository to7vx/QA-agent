# qa-agent

Autonomous AI-powered browser testing agent: given a URL, it explores the page, generates Playwright tests, executes them (with self-healing), and shows everything in a local web dashboard.

## Goal

Replace manual test authoring for web UIs. A QA engineer runs one command — `qa-agent` — the dashboard opens, they paste a URL, pick an LLM provider, and watch the pipeline run live: explore → generate → execute → report.

## Scope

**In:** local web dashboard (primary UX), multi-provider LLM support (Anthropic / OpenAI / Google), self-healing tests, markdown + JSON reports, run history, in-dashboard API key management. CLI subcommands remain for scripting.

**Out (later):** multi-page crawling, CI integration, parallel execution, hosted/multi-user deployment.

## Stack

- Python 3.11+, FastAPI + uvicorn (dashboard backend, binds 127.0.0.1 only)
- Playwright (async API) — browser automation and page capture
- LLM providers behind `providers.LLMProvider`: anthropic (`claude-sonnet-4-6` default), openai, google-genai
- Pydantic v2 — all inter-module data models
- Rich — CLI output only
- React 18 + Vite + TypeScript + Tailwind v4 (`web/` → built into `dashboard/static/`, bundle committed)
- pytest + pytest-asyncio — testing the agent itself
- uv (Python) + npm (frontend build only)

## Architecture

```
src/qa_agent/
├── agent.py        orchestrator — run() full pipeline + run_tests() execute-only; emits RunEvents
├── explorer.py     Playwright page capture → LLM → list[Flow]; public capture_snapshot()
├── generator.py    list[Flow] → LLM → list[TestCase] + writes .py files
├── composer.py     plain-English scenario + URL → one Playwright test (Test Lab backend)
├── executor.py     list[TestCase] → subprocess pytest → list[TestResult]
├── healer.py       selector failures → LLM → repaired selector + re-run
├── reporter.py     Report → markdown file + Rich CLI summary
├── models.py       all Pydantic types: Flow, TestCase, TestResult, Report
├── events.py       RunEvent + EmitFn — progress stream from agent to dashboard
├── store.py        SQLite (reports/qa.db): runs, per-test results, test-case library
├── prompts.py      all LLM prompt strings as module-level constants
├── config.py       Settings (pydantic-settings + dotenv); all provider keys optional
├── keystore.py     ~/.qa-agent/config.json — dashboard-managed API keys + defaults
├── providers/      LLMProvider ABC + anthropic/openai/google adapters + registry
├── dashboard/      FastAPI app: run_manager (store-backed, execute-only runs, rerun-failed),
│   │               api (runs/tests/compose/insights + SSE), server
│   └── static/     built React bundle (committed — end users don't need Node)
└── cli.py          Click entry: `qa-agent` → dashboard; explore/generate/execute/run remain

web/                React frontend source; `npm run build` emits into dashboard/static/
                    pages: NewRun, TestLab, Insights, RunView, History, Settings
```

## Conventions

- **Prompts:** defined in `prompts.py` only — never inline strings passed to providers
- **Providers:** modules never import vendor SDKs directly — always `providers.LLMProvider`
- **Module boundaries:** data crossing between modules must use Pydantic models from `models.py`
- **Playwright:** always async (`async_playwright`, `async def`, `await`)
- **CLI output:** Rich only — no bare `print()` in agent code
- **Config:** env vars go through `config.py:Settings`; dashboard-entered keys through `keystore.py`
- **API keys:** never returned by the HTTP API — masked form only
- **Tests:** `tests/` covers the agent's own logic; generated tests live in `generated_tests/`
- **Frontend:** after editing `web/`, run `npm run build` and commit the updated `dashboard/static/`

## Status

- [x] Full pipeline: explore → generate → execute (self-healing) → report
- [x] Multi-provider LLM layer (Anthropic, OpenAI, Google) + keystore
- [x] Dashboard backend: run manager, REST + SSE API on 127.0.0.1:8899
- [x] Dashboard frontend: New Run, live Run view, History, Settings
- [x] v2: SQLite store (reports/qa.db), Test Lab (AI composer + library),
      Insights, re-run failed, code viewer, model dropdowns
- [ ] Multi-page crawling
- [ ] CI integration

Note: Supabase was considered for the run DB and rejected (free-tier project
limit); the Store class is the single swap point if cloud sync returns.
