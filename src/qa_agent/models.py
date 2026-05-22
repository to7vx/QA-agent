"""Pydantic models for the QA agent domain."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FlowPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Usage(BaseModel):
    """Cumulative LLM token usage and estimated cost for a run."""

    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def add(self, *, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.cost_usd += cost_usd
        self.calls += 1


class FlowStep(BaseModel):
    description: str
    selector: str | None = None
    action: str | None = None
    expected_result: str | None = None


class Flow(BaseModel):
    id: str
    name: str
    description: str
    url: str
    priority: FlowPriority = FlowPriority.MEDIUM
    steps: list[FlowStep] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AuthProfile(BaseModel):
    """A captured login session (Playwright storage_state) for authed testing."""

    id: str
    name: str
    origin: str = ""
    # Playwright storage_state: {"cookies": [...], "origins": [...]}.
    storage_state: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class TestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class TestCase(BaseModel):
    id: str
    flow_id: str
    name: str
    description: str
    playwright_code: str = ""
    file_path: str = ""
    tags: list[str] = Field(default_factory=list)


class HealingAttempt(BaseModel):
    test_case_id: str
    test_case_name: str
    original_selector: str
    new_selector: str | None = None
    confidence: float = 0.0
    reasoning: str = ""
    # healed | failed | refused | error
    outcome: str = "pending"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TestResult(BaseModel):
    test_case_id: str
    test_case_name: str
    status: TestStatus
    duration_ms: float = 0.0
    error_message: str | None = None
    screenshot_path: str | None = None
    stdout: str = ""
    stderr: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    healed: bool = False
    healing: HealingAttempt | None = None


class Report(BaseModel):
    id: str
    url: str
    started_at: datetime
    finished_at: datetime | None = None
    flows: list[Flow] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    results: list[TestResult] = Field(default_factory=list)
    healing_attempts: list[HealingAttempt] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    markdown_path: str = ""

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.PASSED)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.FAILED)

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total * 100) if self.total else 0.0
