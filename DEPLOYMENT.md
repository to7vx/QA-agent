# Deployment

qa-agent is two deployables that share one codebase:

- **API** (`qa-agent-api`) — FastAPI service that runs the pipeline. Needs
  Chromium (baked into the Docker image), Postgres, and a Fernet secret key.
- **Web** (`web/`) — Next.js dashboard. Static-ish front end that talks to the
  API over REST + SSE.

---

## 1. Local full stack (Docker Compose)

The fastest way to run the whole product, no Supabase required:

```bash
# optional: real LLM runs need a provider key
export GEMINI_API_KEY=...        # or ANTHROPIC_API_KEY + QA_AGENT_MODEL=anthropic/...

docker compose up --build
# API   → http://localhost:8000  (/health, /docs)
# Web   → http://localhost:3000
```

Compose starts Postgres, runs Alembic migrations via the API entrypoint, and
launches both services in **no-auth mode** (`QA_AGENT_AUTH_DISABLED=1`) so every
request is treated as one local user. The bundled `QA_AGENT_SECRET_KEY` is a
throwaway dev value — **generate your own for anything real** (see below).

Tear down (and wipe the DB volume):

```bash
docker compose down -v
```

---

## 2. Production

### Secrets you must set

| Variable | Purpose |
|----------|---------|
| `QA_AGENT_DATABASE_URL` | `postgresql+psycopg://USER:PASS@HOST:5432/db` |
| `QA_AGENT_SECRET_KEY` | Fernet key encrypting BYOK keys + auth states at rest |
| `SUPABASE_JWT_SECRET`, `SUPABASE_URL` | Verify dashboard JWTs (omit only if auth-disabled) |
| `QA_AGENT_CORS_ORIGINS` | Comma-separated dashboard origin(s) |
| `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | Default provider key (users can BYOK) |
| `SENTRY_DSN` *(optional)* | Error reporting |
| `QA_AGENT_LOG_LEVEL` *(optional)* | `INFO` (default) / `DEBUG` |

Generate a Fernet key:

```bash
uv run python -c "from qa_agent.api.crypto import generate_key; print(generate_key())"
```

### API → Fly.io / Railway / Render (container)

The `Dockerfile` produces a self-contained API image (Chromium included).

```bash
# Fly.io example
fly launch --no-deploy            # generates fly.toml; set internal_port = 8000
fly secrets set QA_AGENT_DATABASE_URL=... QA_AGENT_SECRET_KEY=... \
               SUPABASE_JWT_SECRET=... SUPABASE_URL=... \
               QA_AGENT_CORS_ORIGINS=https://your-dashboard.vercel.app
fly deploy
```

Railway/Render: point the service at the repo `Dockerfile`, attach a managed
Postgres, set the env vars above. Migrations run automatically on boot
(`docker/entrypoint.sh` → `alembic upgrade head`).

### Web → Vercel

```bash
cd web
vercel                            # link the project
vercel env add NEXT_PUBLIC_API_URL          # https://your-api-host
vercel env add NEXT_PUBLIC_SUPABASE_URL     # from your Supabase project
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY
vercel --prod
```

`NEXT_PUBLIC_*` values are inlined at build time, so set them before building.
Leave the Supabase vars blank only if the API runs with auth disabled.

### Database

Any Postgres 14+ works (Supabase, Neon, RDS, Fly Postgres). The migrations in
`alembic/` create the schema **and the row-level-security policies** that back
multi-tenant isolation — apply them with `alembic upgrade head` (the container
does this for you).

---

## 3. CI

`.github/workflows/ci.yml` runs lint + types + tests (Python) and lint + build
(web) on every push/PR. `.github/workflows/docker.yml` validates that both
images still build. Green CI is the gate before deploying.
