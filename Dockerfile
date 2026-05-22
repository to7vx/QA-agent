# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# qa-agent API service.
#
# Built on Microsoft's Playwright Python image so Chromium + all the OS
# libraries the agent needs to drive a real browser are already present
# (installing them by hand is the painful part of running Playwright in a
# container). uv handles the Python dependency install.
# ---------------------------------------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# uv from the official static image — no curl|sh bootstrap.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    QA_AGENT_API_HOST=0.0.0.0 \
    QA_AGENT_API_PORT=8000

WORKDIR /app

# 1) Dependencies first (cached unless lock/metadata change). No project yet.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --extra api --no-install-project --no-dev --frozen

# 2) Source + migrations, then install the project itself.
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --extra api --no-dev --frozen \
    && chmod +x /usr/local/bin/entrypoint.sh

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

# Runs `alembic upgrade head` (Postgres only) then launches the API.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["qa-agent-api"]
