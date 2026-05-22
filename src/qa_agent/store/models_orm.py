"""SQLAlchemy ORM models for the QA agent store.

Each user-owned table carries ``owner_id``. Column types are DB-portable so the
schema runs on both Postgres (production) and SQLite (tests).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RunORM(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    url: Mapped[str] = mapped_column(Text)
    # queued | running | succeeded | failed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    mode: Mapped[str] = mapped_column(String(16), default="single")  # single | crawl
    auth_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str] = mapped_column(String(128), default="")
    headless: Mapped[bool] = mapped_column(Boolean, default=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Denormalized counts so analytics queries never recompute from children.
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float] = mapped_column(Float, default=0.0)

    # LLM usage / estimated cost for the run (display-only, not billing).
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    markdown_path: Mapped[str] = mapped_column(Text, default="")
    markdown_body: Mapped[str] = mapped_column(Text, default="")
    ai_analysis: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    flows: Mapped[list[FlowORM]] = relationship(back_populates="run", cascade="all, delete-orphan")
    test_cases: Mapped[list[TestCaseORM]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    results: Mapped[list[ResultORM]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    healing_attempts: Mapped[list[HealingAttemptORM]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    events: Mapped[list[RunEventORM]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_runs_owner_created", "owner_id", "created_at"),)


class FlowORM(Base):
    __tablename__ = "flows"

    # Flow ids are unique only within a run → composite primary key.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    steps: Mapped[list] = mapped_column(JSON, default=list)

    run: Mapped[RunORM] = relationship(back_populates="flows")


class TestCaseORM(Base):
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    flow_id: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    playwright_code: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)

    run: Mapped[RunORM] = relationship(back_populates="test_cases")


class ResultORM(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    test_case_id: Mapped[str] = mapped_column(String(64), index=True)
    test_case_name: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    healed: Mapped[bool] = mapped_column(Boolean, default=False)

    run: Mapped[RunORM] = relationship(back_populates="results")


class HealingAttemptORM(Base):
    __tablename__ = "healing_attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    test_case_id: Mapped[str] = mapped_column(String(64), default="")
    test_case_name: Mapped[str] = mapped_column(Text, default="")
    original_selector: Mapped[str] = mapped_column(Text, default="")
    new_selector: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[str] = mapped_column(String(16), default="pending")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    run: Mapped[RunORM] = relationship(back_populates="healing_attempts")


class RunEventORM(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    phase: Mapped[str] = mapped_column(String(16), default="")
    status: Mapped[str] = mapped_column(String(16), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped[RunORM] = relationship(back_populates="events")

    __table_args__ = (Index("ix_run_events_run_seq", "run_id", "seq"),)


class AuthProfileORM(Base):
    __tablename__ = "auth_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text, default="")
    storage_state_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrawlORM(Base):
    __tablename__ = "crawls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    start_url: Mapped[str] = mapped_column(Text)
    max_pages: Mapped[int] = mapped_column(Integer, default=5)
    same_origin: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PageORM(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    crawl_id: Mapped[str] = mapped_column(ForeignKey("crawls.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    depth: Mapped[int] = mapped_column(Integer, default=0)
    discovered_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="discovered")


class UserSettingsORM(Base):
    __tablename__ = "user_settings"

    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    anthropic_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    gemini_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    default_model: Mapped[str] = mapped_column(String(128), default="anthropic/claude-sonnet-4-6")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
