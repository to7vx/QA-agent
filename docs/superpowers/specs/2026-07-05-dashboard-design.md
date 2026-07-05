# qa-agent Dashboard — Design

**Date:** 2026-07-05
**Status:** Approved (user requested full build in one session)

## Summary

Replace the CLI-first workflow with a local web dashboard. A QA engineer runs one
command (`qa-agent`), the browser opens, they paste a URL, pick an LLM provider
(Anthropic / OpenAI / Google), and watch the pipeline run live:
explore → generate → execute (with self-healing) → report. API keys are managed
inside the dashboard — no `.env` editing. Everything a QA engineer needs lives in
one place: new runs, live progress, run history, full run reports, and settings.

## Decisions (from brainstorm)

| Question | Decision |
|---|---|
| Purpose | Full control center — dashboard becomes the product |
| CLI | `qa-agent` launches the dashboard; existing subcommands remain but are de-emphasized |
| Providers | Anthropic (Claude), OpenAI (GPT), Google (Gemini) |
| Stack | FastAPI backend + React/Vite/TypeScript/Tailwind SPA |
| Storage | JSON files on disk — no database (YAGNI) |
| Live updates | Server-Sent Events (SSE) |
| Keys | Stored server-side in `~/.qa-agent/config.json`, masked in UI |

## Architecture

```
src/qa_agent/
├── providers/                 NEW — LLM provider abstraction
│   ├── __init__.py
│   ├── base.py                LLMProvider protocol + provider-agnostic errors
│   ├── anthropic_provider.py
│   ├── openai_provider.py
│   ├── google_provider.py
│   └── registry.py            PROVIDERS catalog, create_provider(), model suggestions
├── keystore.py                NEW — read/write ~/.qa-agent/config.json (keys + defaults)
├── events.py                  NEW — RunEvent model + EventEmitter (thread-safe queue)
├── dashboard/                 NEW — FastAPI app
│   ├── __init__.py
│   ├── server.py              app factory, static mount, uvicorn launcher
│   ├── api.py                 REST + SSE routes
│   ├── run_manager.py         background run lifecycle, event history, history index
│   └── static/                built React bundle (committed)
├── agent.py                   CHANGED — takes LLMProvider, emits RunEvents, writes report.json
├── explorer.py                CHANGED — LLMProvider instead of anthropic client
├── generator.py               CHANGED — same + optional progress callback
├── executor.py                CHANGED — optional per-test callback
├── healer.py                  CHANGED — LLMProvider instead of anthropic client
├── reporter.py                CHANGED — LLMProvider instead of anthropic client
├── config.py                  CHANGED — all provider keys optional; merged with keystore
└── cli.py                     CHANGED — `qa-agent` (no args) launches dashboard

web/                           NEW — React source (Vite + TS + Tailwind)
└── src/ ...                   builds into src/qa_agent/dashboard/static/
```

### Provider layer

Every existing LLM call is the same shape: `(system, user_prompt, max_tokens) → text`.

```python
class LLMProvider(Protocol):
    name: str
    model: str
    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str: ...
```

- `AnthropicProvider` — wraps current `client.messages.create(...)` usage.
- `OpenAIProvider` — `client.chat.completions.create(...)` (system + user messages).
- `GoogleProvider` — `google-genai` SDK, `client.models.generate_content(...)` with
  system instruction.
- Provider-agnostic exceptions: `ProviderAuthError`, `ProviderRateLimitError`,
  `ProviderError`. Each adapter maps its SDK's exceptions to these. Explorer's
  current `anthropic.AuthenticationError` handling switches to these.
- `registry.py` holds the catalog: provider id, label, key env-var name, and
  *suggested* model list (UI offers suggestions but accepts any model string, so
  stale catalogs never block anyone).
- Adapters import their SDK lazily so a missing optional SDK only fails if that
  provider is selected.

### Key storage (keystore.py)

- File: `~/.qa-agent/config.json` — `{"keys": {"anthropic": "...", ...}, "defaults": {"provider": "anthropic", "model": "..."}}`
- Written with best-effort `0600`-style permissions; plaintext local file is the
  accepted trade-off for a local tool (documented in README).
- Precedence: keystore key → env var (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` /
  `GOOGLE_API_KEY`). Env vars still work for CI/power users.
- API never returns a stored key — only `{configured: true, masked: "sk-…abc4"}`.

### Run lifecycle (run_manager.py)

- One active run at a time (`POST /api/runs` returns 409 if busy).
- The run executes in a worker thread via `asyncio.run(QAAgent(...).run(...))` —
  isolated from uvicorn's event loop (also sidesteps Windows loop-policy issues).
- `QAAgent` gains an optional `emit: Callable[[RunEvent], None]`. Emitted events:
  `run_started`, `stage` (explore/generate/execute/report), `flows_found` (payload:
  flows), `test_generated` (per flow), `test_started`, `test_result` (per test,
  includes healing info), `healing` (attempt outcomes), `run_finished` (summary),
  `run_error`, `log` (fine-grained progress lines).
- Generator and Executor get optional callbacks that the agent adapts into events.
  Rich console output stays — it just logs to the server terminal now.
- Events are stored in-memory per run (replay on page refresh / reconnect) and
  appended to `reports/<run_id>/events.jsonl`.
- Cancellation is soft: a flag checked between stages and between tests.
- On finish, the full `Report` is serialized to `reports/<run_id>/report.json`
  alongside the existing markdown. History = scanning those JSON files.

### HTTP API

| Method & path | Purpose |
|---|---|
| `GET /api/providers` | Catalog: providers, suggested models, which have keys |
| `GET /api/settings` | Defaults + masked key status per provider |
| `PUT /api/settings/keys/{provider}` | Save a key (body: `{api_key}`) |
| `DELETE /api/settings/keys/{provider}` | Remove a key |
| `POST /api/settings/keys/{provider}/test` | Live-test the key (1-token completion) |
| `PUT /api/settings/defaults` | Set default provider/model |
| `POST /api/runs` | Start run `{url, provider, model, headed, heal}` → `{run_id}` |
| `GET /api/runs` | Run history (summaries, newest first) |
| `GET /api/runs/{id}` | Full report + status for one run |
| `GET /api/runs/{id}/events` | SSE stream — replays history, then live events |
| `POST /api/runs/{id}/cancel` | Soft-cancel the active run |
| `GET /screenshots/...` | Static mount of the screenshots directory |
| `GET /` (+ SPA routes) | Serves the built React app |

Server binds `127.0.0.1:8899` only (local tool, keys involved — never `0.0.0.0`).

### Frontend (web/ → dashboard/static/)

React 18 + Vite + TypeScript + Tailwind CSS. Minimal deps: `react-router-dom`,
`lucide-react` (icons). Charts (pass-rate ring) are hand-rolled SVG. The built
bundle is committed to `dashboard/static/` so end users need only Python.

**Design language:** dark theme (slate-950 base, indigo/violet accent), Inter for
UI text, JetBrains Mono for selectors/code/URLs, generous spacing, status colors
green/red/amber, subtle transitions on live updates.

**Pages:**

1. **New Run (home, `/`)** — hero URL input with big "Run tests" CTA; provider
   segmented control (Claude / GPT / Gemini) showing key status per provider;
   model select with suggestions + free-text override; toggles: headed browser,
   self-healing. Recent runs strip below. If no key is configured anywhere, an
   onboarding callout walks straight to Settings.
2. **Run view (`/runs/:id`)** — works live *and* for finished runs:
   - Pipeline stepper: Explore → Generate → Execute → Report with per-stage
     status/timing.
   - Flow cards appear as discovered (name, priority badge, steps, tags).
   - Test table ticks live: pending → running → pass/fail, duration, error
     snippet, "healed" badge with old → new selector and confidence.
   - Finished: summary header (pass-rate ring, counts, duration, provider/model),
     AI quality assessment, failure details with screenshots (lightbox), healing
     activity table, link to the markdown report.
3. **History (`/history`)** — table of all runs: pass-rate ring, URL, date,
   provider/model, counts, healed count; click through to run view; filter by URL
   text and status.
4. **Settings (`/settings`)** — per-provider card: masked key input, Save / Remove /
   Test connection (with success/failure feedback), default provider + model.

### Error handling

- Missing/invalid key → run refuses to start with a clear message linking to
  Settings; provider auth errors during a run surface as `run_error` with a
  human-readable message.
- SSE drops → EventSource auto-reconnects; server replays the full event history
  for the run, so the UI is always consistent after reconnect.
- Malformed/legacy report folders are skipped in history (never crash listing).
- Playwright/browser failures already raise `ExplorerError` → become `run_error`.
- Second concurrent run → 409 with "a run is already in progress".

### Testing

- `tests/test_providers.py` — each adapter maps request/response and SDK errors
  correctly (SDKs faked, no network).
- `tests/test_keystore.py` — save/mask/precedence/delete round-trips (tmp dir).
- `tests/test_run_manager.py` — event replay, one-run-at-a-time, history from
  report.json fixtures.
- `tests/test_api.py` — FastAPI TestClient: settings CRUD, run start validation,
  409, history.
- Existing tests keep passing after the provider refactor.
- Frontend: type-checked + built in CI fashion (`tsc && vite build`); no JS unit
  tests in v1.

## Out of scope (this iteration)

Parallel runs, multi-page crawling, auth/multi-user, packaging the dashboard as a
hosted service, editing generated test code in the browser, PDF export.
