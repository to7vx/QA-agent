"""Self-healing layer: detects selector failures and repairs them via Claude."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import anthropic

from .config import Settings
from .models import HealingAttempt, TestCase, TestResult, TestStatus
from .prompts import HEALER_PROMPT, HEALER_SYSTEM

_CONFIDENCE_THRESHOLD = 0.7

# Pytest exit codes that indicate a selector-related failure (not infra errors)
_SELECTOR_FAILURE_STATUSES = {TestStatus.FAILED, TestStatus.ERROR}


class Healer:
    def __init__(
        self,
        settings: Settings,
        client: anthropic.Anthropic,
        model: str,
    ) -> None:
        self.settings = settings
        self.client = client
        self.model = model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def maybe_heal(
        self,
        tc: TestCase,
        result: TestResult,
    ) -> tuple[TestResult, HealingAttempt | None]:
        """Attempt to heal a selector failure.

        Returns (possibly_updated_result, attempt_or_None).
        None means the failure is not selector-related — caller should skip.
        """
        if result.status not in _SELECTOR_FAILURE_STATUSES:
            return result, None

        failing_selector = (result.metadata or {}).get("failing_selector")
        if not failing_selector:
            return result, None  # not a selector failure

        test_code = _read_test_file(tc)
        if not test_code:
            return result, _refused_attempt(tc, failing_selector, "Test source not readable")

        url = _extract_url(test_code)
        if not url:
            return result, _refused_attempt(tc, failing_selector, "Could not extract page URL from test")

        attempt = HealingAttempt(
            test_case_id=tc.id,
            test_case_name=tc.name,
            original_selector=failing_selector,
            outcome="error",
        )

        # Step 1 — re-capture live DOM
        try:
            dom, ax_tree = _capture_dom(url, headless=self.settings.headless)
        except Exception as exc:
            attempt.reasoning = f"DOM capture failed: {exc}"
            return result, attempt

        # Step 2 — ask Claude for a replacement selector
        heal_data = self._ask_claude(test_code, failing_selector, result, dom, ax_tree)
        if heal_data is None:
            attempt.reasoning = "Claude did not return parseable JSON"
            return result, attempt

        attempt.confidence = heal_data.get("confidence", 0.0)
        attempt.reasoning = heal_data.get("reasoning", "")
        attempt.new_selector = heal_data.get("new_selector")

        if heal_data.get("refused"):
            attempt.outcome = "refused"
            attempt.reasoning = heal_data.get("refusal_reason") or attempt.reasoning
            return result, attempt

        if attempt.confidence < _CONFIDENCE_THRESHOLD or not attempt.new_selector:
            attempt.outcome = "refused"
            attempt.reasoning = (
                f"Confidence {attempt.confidence:.2f} is below threshold "
                f"{_CONFIDENCE_THRESHOLD} — refusing to apply"
            )
            return result, attempt

        # Step 3 — rewrite test and re-run
        healed_code = _apply_selector(test_code, failing_selector, attempt.new_selector)
        if healed_code == test_code:
            attempt.outcome = "refused"
            attempt.reasoning = (
                f"Selector 'page.{failing_selector}' not found verbatim in test source"
            )
            return result, attempt

        test_path = Path(tc.file_path)
        original_code = test_path.read_text(encoding="utf-8")
        test_path.write_text(healed_code, encoding="utf-8")

        try:
            new_result = _rerun_test(tc, self.settings)
        except Exception as exc:
            test_path.write_text(original_code, encoding="utf-8")
            attempt.outcome = "error"
            attempt.reasoning = f"Re-run raised exception: {exc}"
            return result, attempt

        if new_result.status == TestStatus.PASSED:
            attempt.outcome = "healed"
            new_result.healed = True
            new_result.healing = attempt
            return new_result, attempt

        # Healing failed — restore original file
        test_path.write_text(original_code, encoding="utf-8")
        attempt.outcome = "failed"
        new_result.healing = attempt
        return new_result, attempt

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ask_claude(
        self,
        test_code: str,
        failing_selector: str,
        result: TestResult,
        dom: str,
        ax_tree: str,
    ) -> dict | None:
        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=HEALER_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": HEALER_PROMPT.format(
                            test_code=test_code[:4_000],
                            failing_selector=failing_selector,
                            error_message=(result.error_message or "")[:500],
                            dom=dom[:8_000],
                            ax_tree=ax_tree[:3_000],
                        ),
                    }
                ],
            )
            raw = msg.content[0].text.strip()
            # Strip markdown fences if Claude added them despite instructions
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw.strip())
            return json.loads(raw)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Healing stats persistence
# ---------------------------------------------------------------------------

def append_healing_stat(report_dir: Path, attempt: HealingAttempt, url: str) -> None:
    """Append one healing attempt to the cumulative healing_stats.json."""
    stats_path = report_dir / "healing_stats.json"
    existing: list[dict] = []
    if stats_path.exists():
        try:
            existing = json.loads(stats_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    existing.append({
        "timestamp": attempt.timestamp.isoformat(),
        "url": url,
        "test_case_name": attempt.test_case_name,
        "original_selector": attempt.original_selector,
        "new_selector": attempt.new_selector,
        "confidence": attempt.confidence,
        "outcome": attempt.outcome,
        "reasoning": attempt.reasoning,
    })

    report_dir.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# DOM capture (sync Playwright — safe to call from sync context)
# ---------------------------------------------------------------------------

def _capture_dom(url: str, *, headless: bool = True) -> tuple[str, str]:
    """Return (html, ax_tree_json) for the given URL using the sync Playwright API."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                pass
            html = page.content()
            ax = page.accessibility.snapshot() or {}
            ax_tree = json.dumps(ax, indent=2)
        finally:
            browser.close()

    return html, ax_tree


# ---------------------------------------------------------------------------
# Test re-execution
# ---------------------------------------------------------------------------

def _rerun_test(tc: TestCase, settings: Settings) -> TestResult:
    import subprocess
    from .executor import _parse_failure, _parse_status

    screenshot_dir = settings.report_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    existing_shots = set(screenshot_dir.rglob("*.png"))

    cmd = [
        sys.executable, "-m", "pytest",
        str(tc.file_path),
        "-v",
        "--tb=long",
        "--no-header",
        "-p", "no:cacheprovider",
        "--screenshot=only-on-failure",
        f"--output={screenshot_dir}",
    ]

    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    duration_ms = (time.monotonic() - t0) * 1_000

    status = _parse_status(proc.returncode)
    combined = proc.stdout + proc.stderr
    error_msg, selector = (
        _parse_failure(combined) if status == TestStatus.FAILED else (None, None)
    )

    new_shots = set(screenshot_dir.rglob("*.png")) - existing_shots
    screenshot = next(iter(sorted(new_shots)), None)

    return TestResult(
        test_case_id=tc.id,
        test_case_name=tc.name,
        status=status,
        duration_ms=duration_ms,
        error_message=error_msg,
        screenshot_path=str(screenshot) if screenshot else None,
        stdout=proc.stdout,
        stderr=proc.stderr,
        metadata={
            "returncode": proc.returncode,
            "failing_selector": selector,
            "cmd": " ".join(cmd),
            "healed_rerun": True,
        },
    )


# ---------------------------------------------------------------------------
# Source manipulation utilities
# ---------------------------------------------------------------------------

def _read_test_file(tc: TestCase) -> str:
    if not tc.file_path:
        return ""
    p = Path(tc.file_path)
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_url(test_code: str) -> str | None:
    """Pull the first page.goto URL out of the test source."""
    m = re.search(r'page\.goto\(\s*["\']([^"\']+)["\']', test_code)
    return m.group(1) if m else None


def _apply_selector(test_code: str, failing_selector: str, new_selector: str) -> str:
    """Replace page.<failing_selector> with <new_selector> in the test source.

    new_selector is a full expression like 'page.get_by_role("button", name="Sign In")'.
    Falls back to quote-normalised matching if the verbatim form is not found.
    """
    old = f"page.{failing_selector}"
    if old in test_code:
        return test_code.replace(old, new_selector)

    # Try with swapped quote style as a fallback
    if '"' in old:
        alt = old.replace('"', "'")
    else:
        alt = old.replace("'", '"')
    if alt in test_code:
        return test_code.replace(alt, new_selector)

    return test_code  # signal: no replacement made


def _refused_attempt(
    tc: TestCase,
    selector: str,
    reason: str,
) -> HealingAttempt:
    return HealingAttempt(
        test_case_id=tc.id,
        test_case_name=tc.name,
        original_selector=selector,
        outcome="refused",
        reasoning=reason,
    )
