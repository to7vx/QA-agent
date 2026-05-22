"""Persistence layer: SQLAlchemy ORM + owner-scoped repository.

The store maps the canonical Pydantic domain models (``qa_agent.models``) to
Postgres so the API and dashboard can serve historical runs and analytics.

Design notes:
- Every user-owned table carries ``owner_id`` (the Supabase ``auth.users.id``).
  The :class:`RunRepository` takes ``owner_id`` on every call and filters all
  reads/writes by it — there is no cross-tenant access path in app code.
  Postgres Row Level Security (added via migration) is defense-in-depth.
- Column types are deliberately DB-portable (``JSON``/``String`` rather than
  ``JSONB``/``ARRAY``/native ``UUID``) so the same ORM runs against in-memory
  SQLite in unit tests and Postgres in production.
- The repository is synchronous: the worker thread writes with a blocking
  session, and the (async) API calls read methods via ``run_in_threadpool``.
"""

from __future__ import annotations

from .engine import Database, make_database
from .repository import RunRepository

__all__ = ["Database", "make_database", "RunRepository"]
