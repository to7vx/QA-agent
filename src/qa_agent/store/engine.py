"""Database engine + session factory.

A thin wrapper around a synchronous SQLAlchemy engine. The worker thread writes
with blocking sessions; the async API calls read methods through a threadpool.

Connection strings:
- Postgres (production / Supabase):  ``postgresql+psycopg://user:pass@host/db``
- SQLite (tests):                    ``sqlite://`` (in-memory) or ``sqlite:///file.db``
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models_orm import Base


class Database:
    """Owns the engine and hands out sessions."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def create_all(self) -> None:
        """Create tables. Used for SQLite tests; production uses Alembic."""
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Transactional scope: commit on success, rollback on error."""
        sess = self._session_factory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    def dispose(self) -> None:
        self.engine.dispose()


def make_database(url: str, *, echo: bool = False) -> Database:
    """Build a :class:`Database` from a connection URL.

    In-memory SQLite needs a shared static pool so every session sees the same
    database (each new connection would otherwise get a fresh empty DB).
    """
    if url.startswith("sqlite") and (
        ":memory:" in url or url in ("sqlite://", "sqlite:///:memory:")
    ):
        engine = create_engine(
            "sqlite://",
            echo=echo,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(url, echo=echo, pool_pre_ping=True)
    return Database(engine)
