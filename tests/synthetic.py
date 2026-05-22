"""Synthetic domain objects for tests — no LLM or browser required.

A compact cousin of ``demo/fake_run.py`` that builds a full :class:`Report`
so persistence, API, and reporter logic can be exercised offline.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from qa_agent.models import (
    Flow,
    FlowPriority,
    FlowStep,
    HealingAttempt,
    Report,
    TestCase,
    TestResult,
    TestStatus,
)

URL = "https://www.saucedemo.com"
STARTED = datetime(2026, 5, 9, 14, 32, 11, tzinfo=UTC)
FINISHED = STARTED + timedelta(seconds=47.3)


def build_report(run_id: str = "run_demo000001") -> Report:
    flows = [
        Flow(
            id="flow_login",
            name="User login with valid credentials",
            description="Standard user logs in and lands on the products page.",
            url=URL,
            priority=FlowPriority.HIGH,
            tags=["auth", "smoke"],
            steps=[
                FlowStep(
                    description="Navigate to login page",
                    action="goto",
                    expected_result="Login form visible",
                ),
                FlowStep(description="Enter username", selector="#user-name", action="fill"),
                FlowStep(
                    description="Submit form",
                    selector="#login-button",
                    action="click",
                    expected_result="Redirect to /inventory.html",
                ),
            ],
        ),
        Flow(
            id="flow_checkout",
            name="Checkout flow completes",
            description="Add item, fill checkout details, finish order.",
            url=URL,
            priority=FlowPriority.HIGH,
            tags=["checkout", "smoke"],
            steps=[FlowStep(description="Click Finish", selector="#finish", action="click")],
        ),
        Flow(
            id="flow_sort",
            name="Sort products by price",
            description="Inventory re-orders cheapest first.",
            url=URL,
            priority=FlowPriority.MEDIUM,
            tags=["inventory"],
            steps=[
                FlowStep(
                    description="Select sort", selector=".product_sort_container", action="select"
                )
            ],
        ),
    ]

    test_cases = [
        TestCase(
            id=f"tc_{f.id}",
            flow_id=f.id,
            name=f.name,
            description=f.description,
            file_path=f"generated_tests/test_{f.id}.py",
            playwright_code="def test_x(page): ...",
            tags=f.tags,
        )
        for f in flows
    ]

    healing = HealingAttempt(
        test_case_id="tc_flow_checkout",
        test_case_name="Checkout flow completes",
        original_selector="#finish",
        new_selector='button[name="finish"]',
        confidence=0.92,
        reasoning="id '#finish' missing; matched stable button[name='finish'].",
        outcome="healed",
    )

    results = [
        TestResult(
            test_case_id="tc_flow_login",
            test_case_name="User login with valid credentials",
            status=TestStatus.PASSED,
            duration_ms=1842,
        ),
        TestResult(
            test_case_id="tc_flow_checkout",
            test_case_name="Checkout flow completes",
            status=TestStatus.PASSED,
            duration_ms=4129,
            healed=True,
            healing=healing,
            metadata={"failing_selector": "#finish"},
        ),
        TestResult(
            test_case_id="tc_flow_sort",
            test_case_name="Sort products by price",
            status=TestStatus.FAILED,
            duration_ms=2890,
            error_message="AssertionError: expected $7.99, got $9.99",
            screenshot_path="reports/screenshots/sort_failed.png",
            metadata={"failing_selector": ".inventory_item_price"},
        ),
    ]

    return Report(
        id=run_id,
        url=URL,
        started_at=STARTED,
        finished_at=FINISHED,
        flows=flows,
        test_cases=test_cases,
        results=results,
        healing_attempts=[healing],
        markdown_path="reports/latest.md",
    )
