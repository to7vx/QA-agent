# qa-agent

Autonomous AI-powered browser testing agent: given a URL, it explores the page, generates Playwright tests, executes them, and produces a markdown report.

## Goal

Build a CLI tool that replaces manual test authoring for web UIs. The agent should be runnable by a developer in under 60 seconds: `qa-agent run <URL>` → working test suite + report.

## v1 Scope

**In:** URL in → explore → generate tests → execute → markdown report

**Out (post-v1):** dashboard, REST API, self-healing tests, multi-page crawling, CI integration, parallel execution

## Stack

- Python 3.11+
- Playwright (async API) — browser automation and page capture
- Anthropic SDK (`claude-sonnet-4-6`) — flow identification and test generation
- Pydantic v2 — all inter-module data models
- Rich — CLI output only
- pytest + pytest-asyncio — testing the agent itself
- uv — package management

## Architecture

```
src/qa_agent/
├── agent.py        orchestrator — ties all modules together, owns the run() loop
├── explorer.py     Playwright page capture → Claude → list[Flow]
├── generator.py    list[Flow] → Claude → list[TestCase] + writes .py files
├── executor.py     list[TestCase] → subprocess pytest → list[TestResult]
├── reporter.py     Report → markdown file + Rich CLI summary
├── models.py       all Pydantic types: Flow, TestCase, TestResult, Report
├── prompts.py      all Claude prompt strings as module-level constants
├── config.py       Settings (pydantic-settings + dotenv)
└── cli.py          Click entry point: `qa-agent run <URL>`
```

## Conventions

- **Prompts:** defined in `prompts.py` only — never inline strings passed to the Anthropic client
- **Module boundaries:** data crossing between modules must use Pydantic models from `models.py`
- **Playwright:** always async (`async_playwright`, `async def`, `await`)
- **CLI output:** Rich only — no bare `print()` in agent code
- **Config:** all env vars go through `config.py:Settings` — no `os.environ` reads elsewhere
- **Tests:** `tests/` covers the agent's own logic; generated tests live in `generated_tests/`

## Status

- [x] Scaffolding complete — all modules exist, models defined, CLI skeleton wired
- [ ] Explorer — in progress next
- [ ] Generator
- [ ] Executor
- [ ] Reporter
- [ ] CLI wired end-to-end
