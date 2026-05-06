"""Pydantic models for the QA agent domain."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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
    steps: list[FlowStep] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


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


class Report(BaseModel):
    id: str
    url: str
    started_at: datetime
    finished_at: datetime | None = None
    flows: list[Flow] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    results: list[TestResult] = Field(default_factory=list)
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
