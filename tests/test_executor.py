"""Unit tests for executor parsing and rendering logic."""

from __future__ import annotations

from qa_agent.executor import _parse_failure, _parse_status, _render_table
from qa_agent.models import TestCase, TestResult, TestStatus

# ---------------------------------------------------------------------------
# _parse_status
# ---------------------------------------------------------------------------


def test_parse_status_passed() -> None:
    assert _parse_status(0) == TestStatus.PASSED


def test_parse_status_failed() -> None:
    assert _parse_status(1) == TestStatus.FAILED


def test_parse_status_no_tests_collected() -> None:
    assert _parse_status(5) == TestStatus.SKIPPED


def test_parse_status_internal_error() -> None:
    assert _parse_status(3) == TestStatus.ERROR


def test_parse_status_interrupted() -> None:
    assert _parse_status(2) == TestStatus.ERROR


# ---------------------------------------------------------------------------
# _parse_failure
# ---------------------------------------------------------------------------

_PLAYWRIGHT_TIMEOUT_OUTPUT = """
FAILED generated_tests/test_login.py::test_user_login - playwright._impl._errors.TimeoutError: Timeout 30000ms exceeded.
=========================== short test summary info ===========================
FAILED generated_tests/test_login.py::test_user_login - playwright._impl._errors.TimeoutError: Timeout 30000ms exceeded.
E   playwright._impl._errors.TimeoutError: Timeout 30000ms exceeded.
E   =========================== logs ===========================
E   waiting for locator('#submit-btn')
E   attempting click action
"""

_ASSERTION_OUTPUT = """
FAILED generated_tests/test_nav.py::test_navigation - AssertionError: assert 'Login' in 'Home Page'
E   AssertionError: assert 'Login' in 'Home Page'
"""

_EXPECT_OUTPUT = """
FAILED generated_tests/test_form.py::test_form - playwright._impl._errors.Error: Timed out 5000ms waiting for expect(locator).to_be_visible()
E     Call log:
E       - expect.to_be_visible with timeout 5000ms
E       - waiting for get_by_role("button", name="Submit")
"""


def test_parse_failure_playwright_timeout() -> None:
    msg, selector = _parse_failure(_PLAYWRIGHT_TIMEOUT_OUTPUT)
    assert msg is not None
    assert "Timeout" in msg or "TimeoutError" in msg
    # _normalise_selector rewrites single → double quotes so the healer can
    # match the selector verbatim against the (double-quoted) Python source.
    assert selector == 'locator("#submit-btn")'


def test_parse_failure_assertion_error() -> None:
    msg, selector = _parse_failure(_ASSERTION_OUTPUT)
    assert msg is not None
    assert "AssertionError" in msg or "assert" in msg.lower()
    assert selector is None


def test_parse_failure_expect_locator() -> None:
    msg, selector = _parse_failure(_EXPECT_OUTPUT)
    assert msg is not None
    assert selector is not None
    assert "get_by_role" in selector


def test_parse_failure_empty_output() -> None:
    msg, selector = _parse_failure("")
    assert msg is None
    assert selector is None


def test_parse_failure_truncates_long_message() -> None:
    long_output = f"FAILED foo::bar - {'E' * 500}\n"
    msg, _ = _parse_failure(long_output)
    assert msg is None or len(msg) <= 303  # 300 + "..."


# ---------------------------------------------------------------------------
# _render_table
# ---------------------------------------------------------------------------


def _make_tc(name: str) -> TestCase:
    return TestCase(id=f"t_{name}", flow_id="f1", name=name, description="")


def test_render_table_all_pending() -> None:
    tcs = [_make_tc("Login"), _make_tc("Search")]
    table = _render_table(tcs, [None, None])
    # Just verify it renders without error — Rich tables don't expose rows easily
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    Console(file=buf, width=120).print(table)
    output = buf.getvalue()
    assert "Login" in output
    assert "Search" in output


def test_render_table_mixed_results() -> None:
    tcs = [_make_tc("A"), _make_tc("B"), _make_tc("C")]
    slots = [
        TestResult(
            test_case_id="t_A", test_case_name="A", status=TestStatus.PASSED, duration_ms=1234
        ),
        TestResult(
            test_case_id="t_B",
            test_case_name="B",
            status=TestStatus.FAILED,
            error_message="selector not found",
        ),
        None,
    ]
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    Console(file=buf, width=120).print(_render_table(tcs, slots))
    output = buf.getvalue()
    assert "PASSED" in output
    assert "FAILED" in output
    assert "selector not found" in output
