"""Demo script: produce a realistic qa-agent run output without the Anthropic API.

Builds synthetic Report / TestResult / HealingAttempt objects and pipes them
through the project's real Reporter — so the CLI panel and the markdown file
are byte-for-byte what a live run would produce, just with fake data.

Run:
    uv run python demo/fake_run.py

Output:
    - Coloured Rich CLI summary in the terminal (screenshot for LinkedIn)
    - Markdown report at demo/output/latest.md  (screenshot the rendered MD)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.console import Console

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
from qa_agent.reporter import Reporter, _render_markdown

console = Console()

URL = "https://www.saucedemo.com"
STARTED = datetime(2026, 5, 9, 14, 32, 11, tzinfo=UTC)
FINISHED = STARTED + timedelta(seconds=47.3)


def build_flows() -> list[Flow]:
    return [
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
                FlowStep(description="Enter password", selector="#password", action="fill"),
                FlowStep(
                    description="Submit form",
                    selector="#login-button",
                    action="click",
                    expected_result="Redirect to /inventory.html",
                ),
            ],
        ),
        Flow(
            id="flow_login_locked",
            name="Locked-out user shows error",
            description="locked_out_user receives an inline error and stays on /.",
            url=URL,
            priority=FlowPriority.HIGH,
            tags=["auth", "negative"],
            steps=[
                FlowStep(
                    description="Submit credentials for locked_out_user",
                    action="fill+click",
                    expected_result="Error banner: 'Sorry, this user has been locked out.'",
                ),
            ],
        ),
        Flow(
            id="flow_add_to_cart",
            name="Add product to cart",
            description="Add a backpack to cart from the inventory grid; badge updates to 1.",
            url=URL,
            priority=FlowPriority.HIGH,
            tags=["cart"],
            steps=[
                FlowStep(description="Login as standard_user", action="login"),
                FlowStep(
                    description="Click Add to cart on the backpack",
                    selector="#add-to-cart-sauce-labs-backpack",
                    action="click",
                ),
                FlowStep(
                    description="Verify cart badge",
                    selector=".shopping_cart_badge",
                    expected_result="Text equals '1'",
                ),
            ],
        ),
        Flow(
            id="flow_checkout",
            name="Checkout flow completes",
            description="Add item, fill checkout details, finish order, see confirmation.",
            url=URL,
            priority=FlowPriority.HIGH,
            tags=["checkout", "smoke"],
            steps=[
                FlowStep(description="Add item, open cart", action="click"),
                FlowStep(description="Click Checkout", selector="#checkout", action="click"),
                FlowStep(description="Fill first name / last name / postal", action="fill"),
                FlowStep(
                    description="Click Finish",
                    selector="#finish",
                    action="click",
                    expected_result="'Thank you for your order!' visible",
                ),
            ],
        ),
        Flow(
            id="flow_sort",
            name="Sort products by price (low to high)",
            description="Inventory re-orders so the cheapest item appears first.",
            url=URL,
            priority=FlowPriority.MEDIUM,
            tags=["inventory"],
            steps=[
                FlowStep(
                    description="Open sort dropdown",
                    selector=".product_sort_container",
                    action="select",
                ),
                FlowStep(
                    description="Select 'Price (low to high)'",
                    action="select",
                    expected_result="First card price is $7.99",
                ),
            ],
        ),
        Flow(
            id="flow_logout",
            name="Logout from menu",
            description="Open burger menu, click Logout, return to login form.",
            url=URL,
            priority=FlowPriority.MEDIUM,
            tags=["auth"],
            steps=[
                FlowStep(
                    description="Open burger menu",
                    selector="#react-burger-menu-btn",
                    action="click",
                ),
                FlowStep(
                    description="Click Logout",
                    selector="#logout_sidebar_link",
                    action="click",
                    expected_result="Redirect to /",
                ),
            ],
        ),
    ]


def build_test_cases(flows: list[Flow]) -> list[TestCase]:
    return [
        TestCase(
            id=f"tc_{f.id}",
            flow_id=f.id,
            name=f.name,
            description=f.description,
            file_path=f"generated_tests/test_{f.id}.py",
            tags=f.tags,
        )
        for f in flows
    ]


def build_results(test_cases: list[TestCase]) -> tuple[list[TestResult], list[HealingAttempt]]:
    healing = HealingAttempt(
        test_case_id="tc_flow_checkout",
        test_case_name="Checkout flow completes",
        original_selector="#finish",
        new_selector="button[name='finish']",
        confidence=0.92,
        reasoning=(
            "The id selector '#finish' returned no matches. The DOM snapshot shows a "
            "<button name='finish'> element in the same form region with identical "
            "label text 'Finish'. High confidence the id was renamed; falling back to "
            "the name attribute is stable across the rest of the checkout form."
        ),
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
            test_case_id="tc_flow_login_locked",
            test_case_name="Locked-out user shows error",
            status=TestStatus.PASSED,
            duration_ms=1310,
        ),
        TestResult(
            test_case_id="tc_flow_add_to_cart",
            test_case_name="Add product to cart",
            status=TestStatus.PASSED,
            duration_ms=2417,
        ),
        TestResult(
            test_case_id="tc_flow_checkout",
            test_case_name="Checkout flow completes",
            status=TestStatus.PASSED,
            duration_ms=4129,
            healed=True,
            healing=healing,
            metadata={"failing_selector": "#finish", "healed_selector": "button[name='finish']"},
        ),
        TestResult(
            test_case_id="tc_flow_sort",
            test_case_name="Sort products by price (low to high)",
            status=TestStatus.FAILED,
            duration_ms=2890,
            error_message=(
                "AssertionError: expected first product price to be $7.99, "
                "got $9.99 — sort option appears not to apply on initial render."
            ),
            screenshot_path="reports/screenshots/sort_failed_20260509_143245.png",
            metadata={"failing_selector": ".inventory_item_price"},
        ),
        TestResult(
            test_case_id="tc_flow_logout",
            test_case_name="Logout from menu",
            status=TestStatus.PASSED,
            duration_ms=1675,
        ),
    ]
    return results, [healing]


def build_ai_analysis() -> str:
    return (
        "**Verdict: Healthy.** 5 of 6 flows pass on the first run, with the checkout "
        "flow recovering automatically after the agent re-derived the `Finish` button "
        "selector (id was renamed; the button's `name` attribute is a stable fallback).\n\n"
        "**One real failure:** the price-sort flow asserts $7.99 as the lowest price but "
        "the page renders $9.99 first. This is not a flaky selector — the sort option "
        "does not apply on initial selection. Reproduce manually before filing: "
        "if confirmed, this is a regression in the inventory ordering logic and should "
        "block release.\n\n"
        "**Coverage gaps to consider next iteration:** problem_user visual regressions, "
        "performance_glitch_user latency assertions, and cart removal."
    )


def build_fix_suggestions() -> dict[str, str]:
    return {
        "tc_flow_sort": (
            "**Root cause:** The `<select>` change event fires before the inventory list "
            "has re-rendered, so the assertion runs against the unsorted DOM. This is a "
            "real product bug, not a test issue — the visible price order does not match "
            "the selected sort option.\n\n"
            "**Suggested fix in the test (defensive):** wait for the first "
            "`.inventory_item_price` text to change before asserting:\n\n"
            "```python\n"
            "await page.locator('.product_sort_container').select_option('lohi')\n"
            "await expect(page.locator('.inventory_item_price').first).to_have_text('$7.99')\n"
            "```\n\n"
            "**Suggested fix in the app:** ensure the inventory store re-emits before "
            "the select change handler resolves, or render the sorted list synchronously."
        ),
    }


def main() -> None:
    flows = build_flows()
    test_cases = build_test_cases(flows)
    results, healing = build_results(test_cases)

    report = Report(
        id="demo00000001",
        url=URL,
        started_at=STARTED,
        finished_at=FINISHED,
        flows=flows,
        test_cases=test_cases,
        results=results,
        healing_attempts=healing,
    )

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    md = _render_markdown(report, build_fix_suggestions(), build_ai_analysis())
    md_path = out_dir / "latest.md"
    md_path.write_text(md, encoding="utf-8")
    report.markdown_path = str(md_path)

    # Re-create the run-style header lines so the screenshot tells the whole story.
    console.print(f"\n[bold cyan]QA Agent[/bold cyan] starting on {URL}\n")
    console.print("[dim]Step 1/4[/dim]  Exploring page and identifying flows...")
    console.print(f"         Found [bold]{len(flows)}[/bold] flows\n")
    console.print("[dim]Step 2/4[/dim]  Generating test cases...")
    console.print(f"         Generated [bold]{len(test_cases)}[/bold] test cases\n")
    console.print("[dim]Step 3/4[/dim]  Writing test files...")
    console.print(
        "         Written to [dim]generated_tests/[/dim]  manifest: [dim]manifest.json[/dim]\n"
    )
    console.print("[dim]Step 4/4[/dim]  Executing tests...  [dim](self-healing enabled)[/dim]\n")

    Reporter(out_dir).print_summary(report)


if __name__ == "__main__":
    main()
