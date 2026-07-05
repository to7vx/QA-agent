# qa-agent Dashboard + Multi-Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CLI-first workflow with a local web dashboard supporting Anthropic, OpenAI, and Google LLM providers.

**Architecture:** A small `LLMProvider` protocol decouples the agent core from the Anthropic SDK; a FastAPI app wraps `QAAgent` with a background run manager streaming SSE events; a React/Vite/Tailwind SPA (built into `dashboard/static/`) is the whole UX. Runs persist as `reports/<run_id>/report.json`; keys live in `~/.qa-agent/config.json`.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, anthropic, openai, google-genai, pydantic v2, React 18, Vite, TypeScript, Tailwind CSS, react-router-dom, lucide-react.

## Global Constraints

- Prompts stay in `prompts.py`; inter-module data uses Pydantic models from `models.py` (CLAUDE.md conventions).
- Server binds `127.0.0.1` only, port 8899.
- API never returns a stored API key; only masked form (`sk-…abc4`).
- Anthropic default model `claude-sonnet-4-6` (project default); suggestions include `claude-opus-4-8`, `claude-haiku-4-5`. OpenAI suggestions: `gpt-5.1`, `gpt-5`, `gpt-5-mini`. Google suggestions: `gemini-2.5-pro`, `gemini-2.5-flash`. Model field always accepts free text.
- One run at a time; second `POST /api/runs` → 409.
- Existing tests in `tests/` must keep passing after the refactor.
- Frontend built output committed to `src/qa_agent/dashboard/static/`.

---

### Task 1: Provider layer (`providers/`)

**Files:**
- Create: `src/qa_agent/providers/__init__.py`, `base.py`, `anthropic_provider.py`, `openai_provider.py`, `google_provider.py`, `registry.py`
- Test: `tests/test_providers.py`

**Interfaces (Produces):**
```python
class LLMProvider(ABC):
    name: str          # "anthropic" | "openai" | "google"
    model: str
    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str: ...

class ProviderError(Exception): ...
class ProviderAuthError(ProviderError): ...
class ProviderRateLimitError(ProviderError): ...

# registry.py
PROVIDERS: dict[str, ProviderInfo]  # id -> {label, key_env, models: list[str], default_model}
def create_provider(provider_id: str, model: str, api_key: str) -> LLMProvider
```
- Each adapter imports its SDK lazily inside `__init__`/`complete`; maps SDK auth/rate-limit exceptions to `ProviderAuthError`/`ProviderRateLimitError`, everything else to `ProviderError`.
- Anthropic adapter reproduces current usage: `client.messages.create(model=…, max_tokens=…, system=…, messages=[{"role":"user","content":prompt}])` → `response.content[0].text`.
- OpenAI: `client.chat.completions.create(model=…, max_completion_tokens=…, messages=[{"role":"system",…},{"role":"user",…}])` → `choices[0].message.content`.
- Google: `genai.Client(api_key=…).models.generate_content(model=…, contents=prompt, config={"system_instruction": system, "max_output_tokens": …})` → `.text`.

Steps: write failing tests (fake SDK objects injected via monkeypatch of the lazy import), run, implement, run green, commit.

### Task 2: Keystore (`keystore.py`)

**Files:** Create `src/qa_agent/keystore.py`; Test `tests/test_keystore.py`

**Interfaces (Produces):**
```python
class KeyStore:
    def __init__(self, path: Path | None = None)  # default ~/.qa-agent/config.json
    def get_key(self, provider: str) -> str | None        # keystore -> env var fallback
    def set_key(self, provider: str, key: str) -> None
    def delete_key(self, provider: str) -> None
    def mask(self, provider: str) -> str | None           # "sk-…abc4"
    def get_defaults(self) -> dict                        # {"provider": str, "model": str}
    def set_defaults(self, provider: str, model: str) -> None
```
Env fallback map: anthropic→ANTHROPIC_API_KEY, openai→OPENAI_API_KEY, google→GOOGLE_API_KEY. TDD with tmp_path.

### Task 3: Run events (`events.py`)

**Files:** Create `src/qa_agent/events.py`; Test `tests/test_events.py`

```python
class RunEvent(BaseModel):
    type: str          # run_started|stage|flows_found|test_generated|test_started|test_result|healing|log|run_finished|run_error|cancelled
    data: dict = {}
    timestamp: datetime  # auto
EmitFn = Callable[[RunEvent], None]
```

### Task 4: Core refactor to LLMProvider + event emission

**Files:**
- Modify: `explorer.py` (ctor takes `LLMProvider`; `_identify_flows` uses `provider.complete`; catch `ProviderAuthError` etc.), `generator.py` (same + optional `on_progress: Callable[[TestCase], None]`), `healer.py` (`LLMProvider` instead of client+model), `reporter.py` (same), `agent.py` (builds provider via `create_provider`, accepts `emit: EmitFn | None` and `cancel: threading.Event | None`, emits events at each stage/test, writes `reports/<run_id>/report.json`), `executor.py` (optional `on_test(tc, result_or_None)` callback), `config.py` (all keys optional; `provider` field; validation moves to call sites), `cli.py` (build provider from settings+keystore; keep commands working)
- Test: existing `tests/` updated; `tests/test_agent_events.py` (agent emits expected sequence with fully mocked modules)

**Interfaces (Produces):**
```python
QAAgent(settings, provider: LLMProvider | None = None, emit: EmitFn | None = None)
async QAAgent.run(url, open_report=False, heal=True, cancel: threading.Event | None = None) -> Report
# report.json: Report.model_dump_json() at reports/<run_id>/report.json plus provider/model in a meta wrapper:
# {"meta": {"provider": ..., "model": ...}, "report": {...Report...}}
```

### Task 5: Run manager + FastAPI app (`dashboard/`)

**Files:**
- Create: `src/qa_agent/dashboard/__init__.py`, `run_manager.py`, `api.py`, `server.py`
- Test: `tests/test_run_manager.py`, `tests/test_api.py` (fastapi TestClient; agent faked)

**Interfaces (Produces):**
```python
class RunManager:
    def start(self, params: RunParams) -> str            # run_id; raises RunBusyError
    def cancel(self, run_id: str) -> bool
    def events_since(self, run_id: str, index: int) -> list[RunEvent]   # replay
    def status(self, run_id: str) -> str                 # running|finished|error|cancelled
    def history(self) -> list[dict]                      # scan reports/*/report.json
    def get_report(self, run_id: str) -> dict | None
```
- Worker thread: `threading.Thread(target=lambda: asyncio.run(agent.run(...)))`; events appended to per-run list + `queue` for SSE; also `reports/<id>/events.jsonl`.
- Endpoints per spec table (providers, settings CRUD + test, runs CRUD, SSE `/api/runs/{id}/events` via `StreamingResponse` media_type `text/event-stream`, screenshots static mount, SPA static mount with index.html fallback).

### Task 6: CLI → dashboard launcher

**Files:** Modify `src/qa_agent/cli.py`, `pyproject.toml` (add fastapi, uvicorn, openai, google-genai deps)
- `qa-agent` with no subcommand → `dashboard` command: uvicorn on 127.0.0.1:8899, `webbrowser.open` after start. Old subcommands remain.

### Task 7: Frontend (`web/` → `dashboard/static/`)

**Files:** Create `web/` Vite React TS app:
- `web/package.json`, `vite.config.ts` (build.outDir `../src/qa_agent/dashboard/static`, proxy `/api` in dev), `tailwind.config`, `index.html`
- `src/api.ts` (typed fetch client + SSE hook `useRunEvents(runId)`)
- `src/types.ts` (mirror Report/Flow/TestResult/RunEvent)
- `src/App.tsx` (router + sidebar shell)
- `src/pages/NewRun.tsx`, `RunView.tsx`, `History.tsx`, `Settings.tsx`
- components: `PipelineStepper`, `FlowCard`, `TestTable`, `PassRing` (SVG), `ProviderPicker`, `KeyCard`
- Design: dark slate-950, indigo accent, JetBrains Mono for code/URLs, status colors green/red/amber.

Steps: scaffold, implement, `npm run build`, verify `tsc` clean, commit built static.

### Task 8: Integration + verification

- `uv sync` (new deps), run full pytest suite green.
- Start server, `GET /api/providers`, `GET /`, verify SPA served and SSE endpoint replays events for a faked run.
- Update `CLAUDE.md` status + architecture, `README` note. Commit.

## Self-Review Notes

- Spec coverage: providers (T1), keystore (T2), events/SSE (T3/T5), core refactor (T4), API (T5), CLI (T6), frontend/UX (T7), error handling embedded in T1/T4/T5, testing per task. Covered.
- Types consistent: `LLMProvider.complete`, `RunEvent`, `EmitFn`, `RunManager` used identically across tasks.
