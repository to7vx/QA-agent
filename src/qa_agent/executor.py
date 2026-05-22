"""Executes generated Playwright test files and collects structured results."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

from rich import box
from rich.console import Console
from rich.live import Live
from rich.table import Table

from .auth import subprocess_env
from .config import Settings
from .events import NULL_EMITTER, EventEmitter
from .models import HealingAttempt, TestCase, TestResult, TestStatus

console = Console()

# Hard timeout per test — Playwright's own 30 s action timeout is the
# first line of defence; this kills genuinely hung processes.
_TEST_TIMEOUT_SECS = 120

_STATUS_STYLE: dict[str, str] = {
    TestStatus.PENDING: "[dim]waiting[/dim]",
    TestStatus.RUNNING: "[cyan]running...[/cyan]",
    TestStatus.PASSED: "[bold green]PASSED[/bold green]",
    TestStatus.FAILED: "[bold red]FAILED[/bold red]",
    TestStatus.ERROR: "[bold red]ERROR[/bold red]",
    TestStatus.SKIPPED: "[yellow]SKIPPED[/yellow]",
}


class Executor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Optional path to a Playwright storage_state file; when set, generated
        # tests run authenticated (the conftest fixture reads QA_STORAGE_STATE_PATH).
        self.storage_state_path: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        test_cases: list[TestCase],
        healer: object | None = None,
        url: str = "",
        emitter: EventEmitter | None = None,
    ) -> tuple[list[TestResult], list[HealingAttempt]]:
        """Run every test case in sequence, showing a live progress table.

        Returns (results, healing_attempts).
        Pass a Healer instance to enable self-healing on selector failures.
        """
        if not test_cases:
            return [], []

        emit = emitter or NULL_EMITTER
        screenshot_dir = self.settings.report_dir / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        slots: list[TestResult | None] = [None] * len(test_cases)
        all_attempts: list[HealingAttempt] = []

        with Live(
            _render_table(test_cases, slots),
            console=console,
            refresh_per_second=8,
            vertical_overflow="visible",
        ) as live:
            for i, tc in enumerate(test_cases):
                slots[i] = _pending_result(tc, TestStatus.RUNNING)
                live.update(_render_table(test_cases, slots))
                emit.emit(
                    "execute",
                    "progress",
                    f"Running {tc.name}",
                    test_case_id=tc.id,
                    test_case_name=tc.name,
                    state="running",
                )

                existing_shots = (
                    set(screenshot_dir.rglob("*.png")) if screenshot_dir.exists() else set()
                )

                try:
                    result = self._run_one(tc, screenshot_dir, existing_shots)
                except Exception as exc:
                    result = TestResult(
                        test_case_id=tc.id,
                        test_case_name=tc.name,
                        status=TestStatus.ERROR,
                        error_message=f"Executor internal error: {exc}",
                    )

                # Self-healing: attempt repair on selector failures
                if healer is not None and result.status in (TestStatus.FAILED, TestStatus.ERROR):
                    slots[i] = _pending_result(tc, TestStatus.RUNNING)  # show as running
                    live.update(_render_table(test_cases, slots))
                    emit.emit(
                        "heal",
                        "start",
                        f"Attempting to heal {tc.name}",
                        test_case_id=tc.id,
                        test_case_name=tc.name,
                    )
                    try:
                        result, attempt = healer.maybe_heal(tc, result)
                    except Exception as exc:
                        attempt = None
                        console.print(f"[yellow]Healer error for {tc.name}: {exc}[/yellow]")
                    if attempt is not None:
                        all_attempts.append(attempt)
                        _write_healing_stat(self.settings.report_dir, attempt, url)
                        if attempt.outcome == "healed":
                            console.print(
                                f"  [green]Healed[/green] {tc.name}: "
                                f"[dim]{attempt.original_selector}[/dim] -> "
                                f"[dim]{attempt.new_selector}[/dim] "
                                f"(confidence {attempt.confidence:.0%})"
                            )
                        emit.emit(
                            "heal",
                            "item_done",
                            f"Heal {attempt.outcome} for {tc.name}",
                            test_case_id=tc.id,
                            test_case_name=tc.name,
                            outcome=attempt.outcome,
                            original_selector=attempt.original_selector,
                            new_selector=attempt.new_selector,
                            confidence=attempt.confidence,
                        )

                slots[i] = result
                live.update(_render_table(test_cases, slots))
                emit.emit(
                    "execute",
                    "item_done",
                    f"{tc.name}: {result.status.value}",
                    test_case_id=tc.id,
                    test_case_name=tc.name,
                    result_status=result.status.value,
                    duration_ms=result.duration_ms,
                    healed=result.healed,
                    error_message=result.error_message,
                )

        return [r for r in slots if r is not None], all_attempts

    def run_parallel(
        self,
        test_cases: list[TestCase],
        healer: object | None = None,
        url: str = "",
        emitter: EventEmitter | None = None,
        max_workers: int = 4,
    ) -> tuple[list[TestResult], list[HealingAttempt]]:
        """Run tests concurrently over a thread pool of pytest subprocesses.

        Each test gets its own screenshot subdir to avoid cross-test races.
        Healing mutates files and re-runs, so it's serialized behind a lock.
        Falls back to sequential :meth:`run` when ``max_workers <= 1`` or there
        is only one test (keeps the live table simple for the common case).
        """
        if not test_cases or max_workers <= 1 or len(test_cases) == 1:
            return self.run(test_cases, healer=healer, url=url, emitter=emitter)

        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        emit = emitter or NULL_EMITTER
        base_dir = self.settings.report_dir / "screenshots"
        base_dir.mkdir(parents=True, exist_ok=True)
        results: dict[str, TestResult] = {}
        all_attempts: list[HealingAttempt] = []
        heal_lock = threading.Lock()
        emit_lock = threading.Lock()

        def work(tc: TestCase) -> TestResult:
            per_test_dir = base_dir / tc.id
            per_test_dir.mkdir(parents=True, exist_ok=True)
            with emit_lock:
                emit.emit(
                    "execute",
                    "progress",
                    f"Running {tc.name}",
                    test_case_id=tc.id,
                    test_case_name=tc.name,
                    state="running",
                )
            try:
                result = self._run_one(tc, per_test_dir, set())
            except Exception as exc:  # noqa: BLE001
                result = TestResult(
                    test_case_id=tc.id,
                    test_case_name=tc.name,
                    status=TestStatus.ERROR,
                    error_message=f"Executor error: {exc}",
                )

            if healer is not None and result.status in (TestStatus.FAILED, TestStatus.ERROR):
                # Serialize healing — it rewrites the test file and re-runs.
                with heal_lock:
                    try:
                        result, attempt = healer.maybe_heal(tc, result)
                    except Exception as exc:  # noqa: BLE001
                        attempt = None
                        console.print(f"[yellow]Healer error for {tc.name}: {exc}[/yellow]")
                    if attempt is not None:
                        all_attempts.append(attempt)
                        _write_healing_stat(self.settings.report_dir, attempt, url)
            return result

        console.print(f"[dim]Running {len(test_cases)} tests with {max_workers} workers...[/dim]")
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="qa-test") as pool:
            futures = {pool.submit(work, tc): tc for tc in test_cases}
            for fut in as_completed(futures):
                tc = futures[fut]
                result = fut.result()
                results[tc.id] = result
                status_str = (
                    "[green]PASS[/green]"
                    if result.status == TestStatus.PASSED
                    else "[red]FAIL[/red]"
                )
                console.print(f"  {status_str}  {tc.name}")
                with emit_lock:
                    emit.emit(
                        "execute",
                        "item_done",
                        f"{tc.name}: {result.status.value}",
                        test_case_id=tc.id,
                        test_case_name=tc.name,
                        result_status=result.status.value,
                        duration_ms=result.duration_ms,
                        healed=result.healed,
                        error_message=result.error_message,
                    )

        # Preserve input order in the returned list.
        ordered = [results[tc.id] for tc in test_cases if tc.id in results]
        return ordered, all_attempts

    def load_from_manifest(self) -> list[TestCase]:
        """Reconstruct TestCase list from generated_tests/manifest.json.
        Falls back to globbing if the manifest does not exist."""
        manifest_path = self.settings.output_dir / "manifest.json"
        if not manifest_path.exists():
            console.print(
                f"[yellow]No manifest found at {manifest_path} — falling back to glob.[/yellow]"
            )
            return self._discover_by_glob()

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        test_cases: list[TestCase] = []
        for entry in data.get("tests", []):
            file_path = self.settings.output_dir / entry["file"]
            if not file_path.exists():
                console.print(f"[yellow]  Skipping missing file: {file_path.name}[/yellow]")
                continue
            # Skip files marked as syntax-invalid — they will crash collection.
            if not entry.get("syntax_valid", True) and not entry.get("repaired", False):
                console.print(f"[yellow]  Skipping syntax-invalid: {file_path.name}[/yellow]")
                continue
            test_cases.append(
                TestCase(
                    id=entry["test_id"],
                    flow_id=entry.get("flow_id", ""),
                    name=entry["flow_name"],
                    description="",
                    file_path=str(file_path),
                    tags=entry.get("tags", []),
                )
            )
        return test_cases

    def save_raw_results(
        self,
        results: list[TestResult],
        healing_attempts: list[HealingAttempt] | None = None,
    ) -> Path:
        """Write results (and healing attempts) to reports/raw_results.json."""
        self.settings.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.report_dir / "raw_results.json"
        payload = {
            "results": [r.model_dump(mode="json") for r in results],
            "healing_attempts": [a.model_dump(mode="json") for a in (healing_attempts or [])],
        }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_one(
        self,
        tc: TestCase,
        screenshot_dir: Path,
        existing_shots: set[Path],
    ) -> TestResult:
        path = Path(tc.file_path)
        if not path.exists():
            return TestResult(
                test_case_id=tc.id,
                test_case_name=tc.name,
                status=TestStatus.ERROR,
                error_message=f"Test file not found: {path}",
            )

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(path),
            "-v",
            "--tb=long",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "--screenshot=only-on-failure",
            f"--output={screenshot_dir}",
        ]

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_TEST_TIMEOUT_SECS,
                env=subprocess_env(self.storage_state_path),
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                test_case_id=tc.id,
                test_case_name=tc.name,
                status=TestStatus.ERROR,
                duration_ms=_TEST_TIMEOUT_SECS * 1_000,
                error_message=f"Test timed out after {_TEST_TIMEOUT_SECS}s",
            )

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
            },
        )

    def _discover_by_glob(self) -> list[TestCase]:
        files = sorted(self.settings.output_dir.glob("test_*.py"))
        return [
            TestCase(
                id=f"test_{f.stem[:12]}",
                flow_id="",
                name=f.stem,
                description="",
                file_path=str(f),
            )
            for f in files
        ]


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


def _parse_status(returncode: int) -> TestStatus:
    """Map pytest exit codes to TestStatus."""
    if returncode == 0:
        return TestStatus.PASSED
    if returncode == 1:
        return TestStatus.FAILED
    if returncode == 5:
        # No tests collected — treat as skipped
        return TestStatus.SKIPPED
    # 2 (interrupted), 3 (internal error), 4 (usage error)
    return TestStatus.ERROR


_CAMEL_GETBY_RE = re.compile(r"getBy([A-Z]\w*)")


def _normalise_selector(sel: str) -> str:
    """Convert Playwright's JS-style call-log selectors to Python form.

    Playwright sometimes logs `getByRole('button', { name: 'Foo' })` even from
    the Python client. The healer looks the selector up verbatim in the test
    source (which uses `get_by_role("button", name="Foo")`), so we rewrite:
      - `getByRole`  → `get_by_role`
      - `{ name: 'Foo' }` → `name="Foo"`
      - single quotes → double quotes
    """
    sel = _CAMEL_GETBY_RE.sub(lambda m: "get_by_" + m.group(1).lower(), sel)
    sel = re.sub(r"\{\s*name\s*:\s*", "name=", sel)
    sel = sel.replace(" }", "").replace("}", "")
    sel = sel.replace("'", '"')
    return sel.strip()


def _parse_failure(output: str) -> tuple[str | None, str | None]:
    """Extract (error_message, failing_selector) from combined pytest output."""
    error_msg: str | None = None
    selector: str | None = None
    lines = output.splitlines()

    # 1. Prefer the summary line: "FAILED path::func - ErrorType: message"
    for line in lines:
        m = re.search(r"FAILED\s+\S+\s+-\s+(.+)$", line)
        if m:
            error_msg = m.group(1).strip()
            break

    # 2. Fallback: last "E   ..." line in the traceback block
    if not error_msg:
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith("E ") and len(stripped) > 3:
                candidate = stripped[2:].strip()
                if any(kw in candidate for kw in ("Error", "error", "assert", "Assert", "Timeout")):
                    error_msg = candidate
                    break

    # 3. Playwright selector — call-log lines look like:
    #      waiting for locator("…")
    #      waiting for get_by_role("button", name="Submit")
    #      waiting for getByRole('button', { name: 'Submit' })   ← JS-style camelCase
    #    We accept all three and normalise camelCase → snake_case so the healer
    #    can find the selector verbatim in the Python test source.
    selector_pattern = re.compile(r"waiting for ((?:locator|get_by_\w+|getBy\w+)\s*\(.+?\))")
    for line in lines:
        m = selector_pattern.search(line)
        if m:
            selector = _normalise_selector(m.group(1))
            break
        # Last-resort: any "- waiting for <something>" tail
        m = re.search(r"-\s+waiting for (.+?)$", line.strip())
        if m:
            selector = _normalise_selector(m.group(1).strip())
            break

    if error_msg and len(error_msg) > 300:
        error_msg = error_msg[:297] + "..."

    return error_msg, selector


# ---------------------------------------------------------------------------
# Rich rendering
# ---------------------------------------------------------------------------


def _render_table(
    test_cases: list[TestCase],
    slots: list[TestResult | None],
) -> Table:
    passed = sum(1 for r in slots if r and r.status == TestStatus.PASSED)
    failed = sum(1 for r in slots if r and r.status in (TestStatus.FAILED, TestStatus.ERROR))
    running = sum(1 for r in slots if r and r.status == TestStatus.RUNNING)
    done = sum(1 for r in slots if r and r.status not in (TestStatus.RUNNING, None))

    title = (
        f"Tests: {done}/{len(test_cases)}  "
        f"[green]{passed} passed[/green]  "
        f"[red]{failed} failed[/red]" + (f"  [cyan]{running} running[/cyan]" if running else "")
    )

    table = Table(
        title=title,
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold",
        expand=True,
        title_justify="left",
    )
    table.add_column("Test name", no_wrap=False, ratio=4)
    table.add_column("Status", justify="center", width=12, no_wrap=True)
    table.add_column("Duration", justify="right", width=10, no_wrap=True)
    table.add_column("Error / Note", ratio=5, no_wrap=False)

    for tc, result in zip(test_cases, slots, strict=False):
        if result is None:
            table.add_row(tc.name, _STATUS_STYLE[TestStatus.PENDING], "", "")
            continue

        status_str = _STATUS_STYLE.get(result.status, result.status.value)
        dur = f"{result.duration_ms:.0f} ms" if result.duration_ms else ""

        if result.status in (TestStatus.FAILED, TestStatus.ERROR):
            err = (result.error_message or "")[:120]
            shot = " [dim][screenshot][/dim]" if result.screenshot_path else ""
            table.add_row(tc.name, status_str, dur, f"[dim]{err}[/dim]{shot}")
        else:
            table.add_row(tc.name, status_str, dur, "")

    return table


def _pending_result(tc: TestCase, status: TestStatus) -> TestResult:
    return TestResult(
        test_case_id=tc.id,
        test_case_name=tc.name,
        status=status,
    )


def _write_healing_stat(report_dir: Path, attempt: HealingAttempt, url: str) -> None:
    """Append a healing attempt to the cumulative healing_stats.json."""
    from .healer import append_healing_stat

    with suppress(Exception):  # never crash the main flow over stats
        append_healing_stat(report_dir, attempt, url)
