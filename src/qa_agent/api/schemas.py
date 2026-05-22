"""Request/response DTOs for the API (distinct from core domain models)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    url: str
    model: str | None = None  # defaults to the user's stored default model
    headless: bool = True
    heal: bool = True
    mode: str = "single"  # single | crawl
    max_pages: int = Field(5, ge=1, le=50)
    auth_profile_id: str | None = None


class RunAccepted(BaseModel):
    run_id: str
    status: str


class RunSummary(BaseModel):
    id: str
    url: str
    status: str
    mode: str
    model: str
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    total: int
    passed: int
    failed: int
    pass_rate: float
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class UserSettingsResponse(BaseModel):
    default_model: str
    has_anthropic_key: bool
    has_gemini_key: bool
    updated_at: str | None = None


class UserSettingsUpdate(BaseModel):
    anthropic_key: str | None = None
    gemini_key: str | None = None
    default_model: str | None = None
    clear_anthropic: bool = False
    clear_gemini: bool = False


class AnalyticsSummary(BaseModel):
    total_runs: int
    tests_total: int
    tests_passed: int
    tests_failed: int
    overall_pass_rate: float
    successful_heals: int
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class TrendPoint(BaseModel):
    run_id: str
    url: str
    created_at: str | None
    pass_rate: float
    total: int
    passed: int
    failed: int


class EventDTO(BaseModel):
    seq: int
    ts: str | None = None
    phase: str
    status: str
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
