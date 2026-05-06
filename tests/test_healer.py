"""Unit tests for healer utility functions."""

from __future__ import annotations

from qa_agent.healer import _apply_selector, _extract_url, _refused_attempt
from qa_agent.models import TestCase


# ---------------------------------------------------------------------------
# _extract_url
# ---------------------------------------------------------------------------

def test_extract_url_double_quotes() -> None:
    code = 'await page.goto("https://example.com/login", wait_until="domcontentloaded")'
    assert _extract_url(code) == "https://example.com/login"


def test_extract_url_single_quotes() -> None:
    code = "await page.goto('https://example.com', wait_until='domcontentloaded')"
    assert _extract_url(code) == "https://example.com"


def test_extract_url_missing() -> None:
    assert _extract_url("# no goto here") is None


# ---------------------------------------------------------------------------
# _apply_selector
# ---------------------------------------------------------------------------

_SAMPLE_CODE = """\
async def test_login(page: Page) -> None:
    await page.goto("https://example.com/login")
    await page.locator('#submit-btn').click()
    await expect(page.locator('#submit-btn')).to_be_visible()
"""


def test_apply_selector_replaces_all_occurrences() -> None:
    new_code = _apply_selector(
        _SAMPLE_CODE,
        "locator('#submit-btn')",
        'page.get_by_role("button", name="Sign In")',
    )
    assert "locator('#submit-btn')" not in new_code
    assert new_code.count('page.get_by_role("button", name="Sign In")') == 2


def test_apply_selector_no_match_returns_original() -> None:
    new_code = _apply_selector(
        _SAMPLE_CODE,
        "locator('#nonexistent')",
        'page.get_by_role("button", name="X")',
    )
    assert new_code == _SAMPLE_CODE


def test_apply_selector_quote_normalisation() -> None:
    code = 'await page.locator("#submit-btn").click()\n'
    # failing_selector uses single quotes but code uses double quotes
    new_code = _apply_selector(
        code,
        "locator('#submit-btn')",
        'page.get_by_role("button", name="Go")',
    )
    assert 'page.get_by_role("button", name="Go")' in new_code


def test_apply_selector_get_by_role() -> None:
    code = 'await page.get_by_role("button", name="Submit").click()\n'
    new_code = _apply_selector(
        code,
        'get_by_role("button", name="Submit")',
        'page.get_by_role("button", name="Sign In")',
    )
    assert 'page.get_by_role("button", name="Sign In")' in new_code


# ---------------------------------------------------------------------------
# _refused_attempt
# ---------------------------------------------------------------------------

def _make_tc(name: str = "login") -> TestCase:
    return TestCase(id="t1", flow_id="f1", name=name, description="")


def test_refused_attempt_fields() -> None:
    tc = _make_tc()
    a = _refused_attempt(tc, "locator('#x')", "element gone")
    assert a.outcome == "refused"
    assert a.original_selector == "locator('#x')"
    assert a.reasoning == "element gone"
    assert a.test_case_id == "t1"
    assert a.new_selector is None
