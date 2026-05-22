# qa-agent

Autonomous AI-powered browser testing agent: given a URL, it explores the page, generates Playwright tests, executes them, and produces a markdown report.

## Goal

Started as a CLI that replaces manual test authoring for web UIs (`qa-agent run <URL>` →
working test suite + report). Now also a **multi-tenant SaaS**: a FastAPI service +
Next.js dashboard wrapping the same pipeline, with persisted run history, analytics, BYOK
keys, authenticated flows, and multi-page crawl + parallel execution.

## Scope

**CLI (v1, done):** URL in → explore → generate tests → execute → self-heal → markdown report

**Full product (done):** FastAPI REST API + SSE progress streaming, Postgres/Supabase
persistence, Next.js dashboard, Supabase auth (multi-tenant, owner-scoped + RLS), BYOK
provider keys, authenticated flows (storage_state), multi-page crawl, parallel execution.

## Stack

- Python 3.11+ · Playwright (async API) · LiteLLM (Claude **or** Gemini) · Pydantic v2
- Rich (CLI output) · Click (CLI) · pytest + pytest-asyncio
- **API:** FastAPI · SQLAlchemy 2.0 · Alembic · asyncpg/psycopg · sse-starlette · PyJWT · cryptography (Fernet)
- **Web:** Next.js 14 (App Router) · TanStack Query · Recharts · Tailwind · @supabase/ssr
- uv — package management

## Architecture

```
src/qa_agent/
├── agent.py        orchestrator — owns run(); emits ProgressEvents; CLI-safe
├── explorer.py     Playwright capture → LLM → list[Flow]  (_capture_from_page reused by crawler)
├── crawler.py      BFS same-origin crawl → flows per page (reuses explorer)
├── generator.py    list[Flow] → LLM → list[TestCase] + writes .py files (+ storage_state conftest)
├── executor.py     list[TestCase] → subprocess pytest → list[TestResult]; run_parallel()
├── healer.py       selector-failure repair (confidence-gated, audited)
├── reporter.py     Report → markdown file + Rich CLI summary
├── events.py       ProgressEvent / EventEmitter (pipeline → SSE/persistence)
├── auth.py         capture/inject Playwright storage_state (authenticated flows)
├── models.py       Pydantic types: Flow, TestCase, TestResult, Report, AuthProfile, …
├── prompts.py      all LLM prompt strings as module-level constants
├── config.py       core Settings (pydantic-settings + dotenv)
├── cli.py          Click entry: run / explore / generate / execute / auth capture
├── store/          SQLAlchemy ORM + owner-scoped RunRepository + engine/mappers
└── api/            FastAPI app: routers, JobManager, EventBus, auth (Supabase JWT),
                    BYOK (byok.py), profiles, SSRF guard (security.py), crypto
alembic/            migrations (initial schema + Postgres RLS policies)
web/                Next.js dashboard (Vercel)
```

Entry points: `qa-agent` (CLI) and `qa-agent-api` (FastAPI service).

## Conventions

- **Prompts:** defined in `prompts.py` only — never inline strings passed to the LLM client
- **Module boundaries:** data crossing between modules must use Pydantic models from `models.py`
- **Playwright:** exploration/crawl async; healer uses sync API (safe from sync executor)
- **CLI output:** Rich only — no bare `print()` in agent code
- **Config:** core env vars through `config.py:Settings`; API-only config in `api/settings.py:ApiSettings`
- **Pipeline stays CLI-safe & DB-agnostic:** the API *injects* progress hooks, per-user
  BYOK keys, and auth — `agent.py` never imports `api`/`store`. `on_event=None` → CLI unchanged.
- **Multi-tenancy:** every store row carries `owner_id`; `RunRepository` filters by it on
  every call; Postgres RLS is defense-in-depth. Never add a cross-tenant read path.
- **Secrets:** provider keys + storage states are Fernet-encrypted at rest; never returned
  to clients or logged. User-submitted URLs pass `security.validate_target_url` (SSRF).
- **Tests:** `tests/` covers the agent + store + API (offline via fakes; SQLite, no Docker);
  generated tests live in `generated_tests/`.

## Status

- [x] CLI pipeline (explore → generate → execute → self-heal → report)
- [x] Persistence layer (SQLAlchemy + Alembic, owner-scoped) + Postgres RLS
- [x] FastAPI service: runs/analytics/settings/auth-profiles, SSE streaming, JobManager
- [x] Supabase auth (multi-tenant) + BYOK provider keys + SSRF guard + per-user quotas
- [x] Next.js dashboard (overview, runs, live run detail, analytics, settings, login)
- [x] Authenticated flows (storage_state capture + injection)
- [x] Multi-page crawl + parallel execution
- [x] 75 tests passing (`uv run pytest`)
