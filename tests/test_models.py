"""Basic tests for Pydantic models."""

from datetime import datetime, timezone

import pytest

from qa_agent.models import (
    Flow,
    FlowPriority,
    FlowStep,
    Report,
    TestCase,
    TestResult,
    TestStatus,
)


def test_flow_step_optional_fields() -> None:
    step = FlowStep(description="Click login button")
    assert step.selector is None
    assert step.action is None


def test_flow_priority_default() -> None:
    flow = Flow(id="f1", name="Login", description="User logs in", url="https://example.com")
    assert flow.priority == FlowPriority.MEDIUM
    assert flow.priority.value == "medium"


def test_flow_priority_from_string() -> None:
    flow = Flow(
        id="f2",
        name="Checkout",
        description="User checks out",
        url="https://example.com",
        priority="high",
    )
    assert flow.priority == FlowPriority.HIGH
    assert flow.priority == "high"  # str Enum equality


def test_flow_priority_values() -> None:
    assert FlowPriority.HIGH == "high"
    assert FlowPriority.MEDIUM == "medium"
    assert FlowPriority.LOW == "low"


def test_flow_roundtrip() -> None:
    flow = Flow(
        id="flow_abc123",
        name="Login",
        description="User logs in",
        url="https://example.com",
        priority="high",
        steps=[FlowStep(description="Fill email", action="fill")],
        tags=["auth"],
    )
    dumped = flow.model_dump()
    restored = Flow(**dumped)
    assert restored.id == flow.id
    assert restored.priority == FlowPriority.HIGH
    assert len(restored.steps) == 1


def test_test_case_defaults() -> None:
    tc = TestCase(
        id="test_001",
        flow_id="flow_abc",
        name="Login test",
        description="Tests the login flow",
    )
    assert tc.playwright_code == ""
    assert tc.tags == []


def test_report_pass_rate_empty() -> None:
    report = Report(
        id="rep_001",
        url="https://example.com",
        started_at=datetime.now(timezone.utc),
    )
    assert report.pass_rate == 0.0
    assert report.total == 0


def test_report_pass_rate() -> None:
    now = datetime.now(timezone.utc)
    results = [
        TestResult(test_case_id="t1", test_case_name="A", status=TestStatus.PASSED),
        TestResult(test_case_id="t2", test_case_name="B", status=TestStatus.PASSED),
        TestResult(test_case_id="t3", test_case_name="C", status=TestStatus.FAILED),
    ]
    report = Report(id="rep_002", url="https://example.com", started_at=now, results=results)
    assert report.total == 3
    assert report.passed == 2
    assert report.failed == 1
    assert abs(report.pass_rate - 66.67) < 0.1


def test_test_status_values() -> None:
    assert TestStatus.PASSED == "passed"
    assert TestStatus.FAILED == "failed"
