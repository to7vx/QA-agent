# Security

qa-agent runs a browser against user-supplied URLs, stores third-party API
keys, and is multi-tenant. This documents the threat model it's built against
and how to report issues.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security → Advisories) or
email the maintainer rather than filing a public issue. Include reproduction
steps and impact. We aim to acknowledge within a few days.

## Threat model & controls

### SSRF — server fetching attacker-chosen URLs
The whole product takes a URL and loads it in a real browser, so SSRF is the
headline risk. `api/security.py:validate_target_url` is applied before any run:

- Only `http`/`https` schemes.
- Rejects loopback, private (RFC1918), link-local, multicast, and reserved IPs.
- Resolves DNS and re-checks the resolved address, defeating DNS-rebinding.

### Multi-tenant isolation
- Every owned row carries `owner_id`; `RunRepository` filters by it on **every**
  read and write — there is no cross-tenant read path.
- Postgres **row-level security** policies (`alembic/versions/*_rls_policies.py`)
  enforce the same constraint at the database, as defense-in-depth.
- JWTs minted by Supabase are verified (`api/auth.py`) with signature, expiry,
  and audience checks.

### Secrets at rest
- BYOK provider keys and captured auth `storage_state` are **Fernet-encrypted**
  (`api/crypto.py`) before storage and decrypted only in memory.
- Secrets are never returned to clients or written to logs.
- `QA_AGENT_SECRET_KEY` must be set in production; without it the server uses an
  ephemeral key (logged loudly) and stored secrets won't survive a restart.

### Abuse / DoS
- Per-IP rate limiting (`slowapi`), configurable via `QA_AGENT_RATE_LIMIT`.
- Per-user concurrency cap and daily run cap enforced server-side.
- CORS is restricted to configured dashboard origins.

### Generated & executed code
- The agent generates Playwright tests and runs them via `pytest` subprocesses.
  Generated code is the agent's own output driving a browser — it is not
  attacker-controlled input executed on the host beyond the sandboxed run.

## Operational notes

- `QA_AGENT_AUTH_DISABLED=1` removes authentication and treats every request as
  one local user. It also disables rate limiting. **Never enable it in
  production** — it exists for local development and the Docker demo only.
- Set `SENTRY_DSN` to capture errors; request IDs (`X-Request-ID`) correlate
  logs across a request.
