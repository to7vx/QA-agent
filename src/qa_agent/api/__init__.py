"""FastAPI service that wraps the QA agent pipeline as a multi-tenant SaaS.

The API never reimplements pipeline logic — it triggers ``QAAgent.run`` on a
background worker, streams progress over SSE, and persists results per user
(BYOK keys, owner-scoped data, SSRF-guarded target URLs).
"""
