# Contributing

Thanks for your interest in qa-agent. This is a portfolio project, but issues
and PRs are welcome.

## Setup

```bash
# Python (CLI + API)
uv sync --extra api --group dev
uv run playwright install chromium

# Git hooks (ruff + mypy on commit)
uv run pre-commit install

# Web dashboard
cd web && npm install
```

## Day-to-day commands

| Task | Command |
|------|---------|
| Run tests | `uv run pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type-check | `uv run mypy src` |
| Run the CLI | `uv run qa-agent run <URL>` |
| Run the API | `uv run qa-agent-api` (add `QA_AGENT_AUTH_DISABLED=1` for local) |
| Web dev server | `cd web && npm run dev` |
| Full stack | `docker compose up --build` |

## Conventions

These are enforced by review (and most by CI). The project-level rules live in
`CLAUDE.md`; the highlights:

- **Prompts** live in `prompts.py` only — never inline LLM strings.
- **Module boundaries:** data crossing modules uses Pydantic models from
  `models.py`. The pipeline stays CLI-safe and DB-agnostic — `agent.py` must
  never import `api/` or `store/`.
- **Multi-tenancy:** every store row carries `owner_id` and is filtered by it.
  Never add a cross-tenant read path.
- **Secrets** are Fernet-encrypted at rest and never logged or returned.
- New code should pass `ruff`, `ruff format`, and `mypy` (the browser-glue
  modules are relaxed in `mypy` config; new API/store/models code is checked).

## Pull requests

1. Branch off `master`.
2. Keep changes focused; add tests for new behavior (`tests/` runs offline —
   no real browser, LLM, or Postgres needed).
3. Make sure CI is green: `uv run ruff check . && uv run mypy src && uv run pytest`
   and, for web changes, `cd web && npm run lint && npm run build`.
4. Open the PR with a clear description of the change and its motivation.
