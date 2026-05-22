"""Pure conversion functions between Pydantic domain models and ORM rows.

Keeping these separate means ``qa_agent.models`` and the pipeline stay totally
unaware of the database.
"""

from __future__ import annotations

import uuid

from ..models import (
    Flow,
    FlowPriority,
    FlowStep,
    HealingAttempt,
    Report,
    TestCase,
    TestResult,
    TestStatus,
    Usage,
)
from .models_orm import (
    FlowORM,
    HealingAttemptORM,
    ResultORM,
    RunORM,
    TestCaseORM,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --- domain -> ORM ---------------------------------------------------------


def flow_to_orm(flow: Flow, *, run_id: str, owner_id: str) -> FlowORM:
    dumped = flow.model_dump(mode="json")
    return FlowORM(
        id=flow.id,
        run_id=run_id,
        owner_id=owner_id,
        name=flow.name,
        description=flow.description,
        url=flow.url,
        priority=flow.priority.value,
        tags=list(flow.tags),
        steps=dumped["steps"],
    )


def test_case_to_orm(tc: TestCase, *, run_id: str, owner_id: str) -> TestCaseORM:
    return TestCaseORM(
        id=tc.id,
        run_id=run_id,
        owner_id=owner_id,
        flow_id=tc.flow_id,
        name=tc.name,
        description=tc.description,
        playwright_code=tc.playwright_code,
        file_path=tc.file_path,
        tags=list(tc.tags),
    )


def result_to_orm(result: TestResult, *, run_id: str, owner_id: str) -> ResultORM:
    return ResultORM(
        id=_new_id("res"),
        run_id=run_id,
        owner_id=owner_id,
        test_case_id=result.test_case_id,
        test_case_name=result.test_case_name,
        status=result.status.value,
        duration_ms=result.duration_ms,
        error_message=result.error_message,
        screenshot_path=result.screenshot_path,
        stdout=result.stdout,
        stderr=result.stderr,
        meta=dict(result.metadata),
        healed=result.healed,
    )


def healing_to_orm(h: HealingAttempt, *, run_id: str, owner_id: str) -> HealingAttemptORM:
    return HealingAttemptORM(
        id=_new_id("heal"),
        run_id=run_id,
        owner_id=owner_id,
        test_case_id=h.test_case_id,
        test_case_name=h.test_case_name,
        original_selector=h.original_selector,
        new_selector=h.new_selector,
        confidence=h.confidence,
        reasoning=h.reasoning,
        outcome=h.outcome,
        timestamp=h.timestamp,
    )


# --- ORM -> domain ---------------------------------------------------------


def orm_to_flow(row: FlowORM) -> Flow:
    return Flow(
        id=row.id,
        name=row.name,
        description=row.description,
        url=row.url,
        priority=FlowPriority(row.priority),
        steps=[FlowStep(**s) for s in (row.steps or [])],
        tags=list(row.tags or []),
    )


def orm_to_test_case(row: TestCaseORM) -> TestCase:
    return TestCase(
        id=row.id,
        flow_id=row.flow_id,
        name=row.name,
        description=row.description,
        playwright_code=row.playwright_code,
        file_path=row.file_path,
        tags=list(row.tags or []),
    )


def orm_to_healing(row: HealingAttemptORM) -> HealingAttempt:
    return HealingAttempt(
        test_case_id=row.test_case_id,
        test_case_name=row.test_case_name,
        original_selector=row.original_selector,
        new_selector=row.new_selector,
        confidence=row.confidence,
        reasoning=row.reasoning,
        outcome=row.outcome,
        timestamp=row.timestamp,
    )


def orm_to_result(row: ResultORM, healing: HealingAttempt | None = None) -> TestResult:
    return TestResult(
        test_case_id=row.test_case_id,
        test_case_name=row.test_case_name,
        status=TestStatus(row.status),
        duration_ms=row.duration_ms,
        error_message=row.error_message,
        screenshot_path=row.screenshot_path,
        stdout=row.stdout,
        stderr=row.stderr,
        metadata=dict(row.meta or {}),
        healed=row.healed,
        healing=healing,
    )


def orm_to_report(run: RunORM) -> Report:
    """Reconstruct a full domain :class:`Report` from a run row + children."""
    healing_by_tc: dict[str, HealingAttempt] = {}
    healing_attempts = [orm_to_healing(h) for h in run.healing_attempts]
    for h in healing_attempts:
        healing_by_tc[h.test_case_id] = h

    results = [
        orm_to_result(r, healing_by_tc.get(r.test_case_id) if r.healed else None)
        for r in run.results
    ]

    return Report(
        id=run.id,
        url=run.url,
        started_at=run.started_at,
        finished_at=run.finished_at,
        flows=[orm_to_flow(f) for f in run.flows],
        test_cases=[orm_to_test_case(t) for t in run.test_cases],
        results=results,
        healing_attempts=healing_attempts,
        usage=Usage(
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
            cost_usd=run.cost_usd,
        ),
        markdown_path=run.markdown_path,
    )
