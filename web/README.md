# QA Agent Dashboard

Next.js (App Router) dashboard for the QA Agent API. Live run progress over SSE,
pass-rate trends, healing analytics, BYOK settings, and Supabase auth.

## Setup

```bash
cd web
npm install
cp .env.local.example .env.local   # edit NEXT_PUBLIC_API_URL (+ Supabase if used)
npm run dev                        # http://localhost:3000
```

Start the API separately (from the repo root):

```bash
# local no-auth mode (no Supabase needed)
QA_AGENT_AUTH_DISABLED=1 QA_AGENT_DATABASE_URL=sqlite:///qa_agent.db uv run qa-agent-api
```

Then leave `NEXT_PUBLIC_SUPABASE_*` blank in `.env.local` — the dashboard runs
in local no-auth mode and talks to the auth-disabled API.

## Production

- Deploy this `web/` folder to **Vercel**.
- Set `NEXT_PUBLIC_API_URL` to the deployed API origin, and the
  `NEXT_PUBLIC_SUPABASE_*` vars to your Supabase project.
- Deploy the Python API to a container host (it runs browsers + pytest
  subprocesses and can't run on Vercel serverless).

## Routes

| Path | Purpose |
|------|---------|
| `/` | KPI cards + pass-rate trend + recent runs |
| `/runs` | Run history |
| `/runs/new` | Trigger a run (single/crawl, heal, headless) |
| `/runs/[id]` | Live SSE progress, results, healing, flows |
| `/analytics` | Trends + healing outcomes |
| `/settings` | BYOK provider keys + default model |
| `/login` | Supabase email/password + OAuth |
