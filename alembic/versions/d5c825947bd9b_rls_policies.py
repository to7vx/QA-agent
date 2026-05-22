"""row-level security policies (Postgres only)

Enables RLS on every user-owned table so a tenant can only ever see rows where
``owner_id`` matches their Supabase auth id (``auth.uid()``). This is
defense-in-depth on top of the application-level ``owner_id`` filtering in
``RunRepository``. No-op on SQLite (used by tests).

Revision ID: e1a2b3c4d5e6
Revises: d5c825947bd9
Create Date: 2026-05-21 08:10:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "d5c825947bd9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables that carry owner_id and must be tenant-isolated.
_OWNED_TABLES = [
    "runs",
    "flows",
    "test_cases",
    "results",
    "healing_attempts",
    "run_events",
    "auth_profiles",
    "crawls",
    "pages",
    "user_settings",
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    for table in _OWNED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # Supabase exposes the authenticated user id via auth.uid() (uuid).
        # owner_id is stored as text, so cast for comparison.
        op.execute(
            f"""
            CREATE POLICY {table}_owner_isolation ON {table}
            USING (owner_id = auth.uid()::text)
            WITH CHECK (owner_id = auth.uid()::text)
            """
        )


def downgrade() -> None:
    if not _is_postgres():
        return
    for table in _OWNED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
