"""Produces markdown reports from test results."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import anthropic
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import HealingAttempt, Report, TestResult, TestStatus
from .prompts import (
    ANALYZE_FAILURE_PROMPT,
    ANALYZE_FAILURE_SYSTEM,
    REPORTER_ANALYSIS_PROMPT,
    REPORTER_ANALYSIS_SYSTEM,
)

if TYPE_CHECKING:
    pass

console = Console()

_STATUS_ICON = {
    TestStatus.PASSED:  "PASSED",
    TestStatus.FAILED:  "FAILED",
    TestStatus.ERROR:   "ERROR",
    TestStatus.SKIPPED: "SKIPPED",
    TestStatus.PENDING: "PENDING",
    TestStatus.RUNNING: "RUNNING",
}


class Reporter:
    def __init__(
        self,
        report_dir: Path,
        client: anthropic.Anthropic | None = None,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self.report_dir = report_dir
        self.client = client
        self.model = model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def finalize(self, report: Report, open_after: bool = False) -> Report:
        report.finished_at = datetime.now(timezone.utc)
        self.report_dir.mkdir(parents=True, exist_ok=True)

        # Per-failure AI analysis (only if client available)
        fix_suggestions: dict[str, str] = {}
        if self.client:
            fix_suggestions = self._get_fix_suggestions(report)

        # Overall AI verdict
        ai_analysis = ""
        if self.client:
            ai_analysis = self._get_ai_analysis(report)

        md = _render_markdown(report, fix_suggestions, ai_analysis)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        named_path = self.report_dir / f"report_{ts}_{report.id[:8]}.md"
        latest_path = self.report_dir / "latest.md"

        named_path.write_text(md, encoding="utf-8")
        latest_path.write_text(md, encoding="utf-8")
        report.markdown_path = str(named_path)

        if open_after:
            _open_report(named_path)

        return report

    def print_summary(self, report: Report) -> None:
        passed = report.passed
        failed = report.failed
        total = report.total
        rate = report.pass_rate

        verdict_style = (
            "bold green" if failed == 0
            else "bold yellow" if rate >= 50
            else "bold red"
        )
        verdict_text = (
            "[bold green]All tests passed[/bold green]" if failed == 0
            else f"[bold red]{failed} test(s) failed[/bold red]"
        )

        duration = ""
        if report.finished_at:
            secs = (report.finished_at - report.started_at).total_seconds()
            duration = f"  Duration: {secs:.1f}s"

        # Results table
        table = Table(
            box=box.SIMPLE_HEAVY,
            show_header=True,
            header_style="bold",
            expand=True,
        )
        table.add_column("Test", ratio=5)
        table.add_column("Status", justify="center", width=10, no_wrap=True)
        table.add_column("Duration", justify="right", width=10, no_wrap=True)
        table.add_column("Error / Note", ratio=5)

        for result in report.results:
            status_str = {
                TestStatus.PASSED:  "[bold green]PASSED[/bold green]",
                TestStatus.FAILED:  "[bold red]FAILED[/bold red]",
                TestStatus.ERROR:   "[bold red]ERROR[/bold red]",
                TestStatus.SKIPPED: "[yellow]SKIPPED[/yellow]",
            }.get(result.status, result.status.value)

            dur = f"{result.duration_ms:.0f} ms" if result.duration_ms else ""
            err = (result.error_message or "")[:100]

            table.add_row(result.test_case_name, status_str, dur, f"[dim]{err}[/dim]" if err else "")

        console.print(
            Panel(
                table,
                title=f"[bold]QA Results[/bold]  {verdict_text}",
                subtitle=(
                    f"[{verdict_style}]{passed}/{total} passed ({rate:.0f}%)[/{verdict_style}]"
                    f"{duration}"
                ),
                border_style="green" if failed == 0 else "red",
                padding=(1, 2),
            )
        )

        # Self-healing summary
        if report.healing_attempts:
            healed = sum(1 for a in report.healing_attempts if a.outcome == "healed")
            refused = sum(1 for a in report.healing_attempts if a.outcome == "refused")
            failed = sum(1 for a in report.healing_attempts if a.outcome == "failed")
            console.print(
                f"[bold]Self-healing:[/bold]  "
                f"[green]{healed} healed[/green]  "
                f"[yellow]{refused} refused[/yellow]  "
                f"[red]{failed} failed[/red]"
            )

        if report.markdown_path:
            console.print(f"Report: [dim]{report.markdown_path}[/dim]")
            console.print(f"Latest: [dim]{Path(report.markdown_path).parent / 'latest.md'}[/dim]\n")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_fix_suggestions(self, report: Report) -> dict[str, str]:
        """Call Claude once per failed test to get a root cause and fix."""
        suggestions: dict[str, str] = {}
        failures = [r for r in report.results if r.status in (TestStatus.FAILED, TestStatus.ERROR)]

        if not failures:
            return suggestions

        for result in failures:
            test_code = _load_test_code(result)
            error_output = _build_error_output(result)

            if not test_code and not error_output:
                continue

            try:
                msg = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=ANALYZE_FAILURE_SYSTEM,
                    messages=[
                        {
                            "role": "user",
                            "content": ANALYZE_FAILURE_PROMPT.format(
                                test_code=test_code or "(source not available)",
                                error_output=error_output or "(no error output captured)",
                            ),
                        }
                    ],
                )
                suggestions[result.test_case_id] = msg.content[0].text.strip()
            except Exception:
                pass  # best-effort; skip silently

        return suggestions

    def _get_ai_analysis(self, report: Report) -> str:
        """Call Claude for an overall quality verdict."""
        flows_summary = _build_flows_summary(report)
        failures_summary = _build_failures_summary(report)

        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=REPORTER_ANALYSIS_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": REPORTER_ANALYSIS_PROMPT.format(
                            url=report.url,
                            total=report.total,
                            passed=report.passed,
                            pass_rate=f"{report.pass_rate:.1f}",
                            failed=report.failed,
                            flows_summary=flows_summary,
                            failures_summary=failures_summary,
                        ),
                    }
                ],
            )
            return msg.content[0].text.strip()
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_markdown(
    report: Report,
    fix_suggestions: dict[str, str],
    ai_analysis: str,
) -> str:
    duration = ""
    if report.finished_at:
        secs = (report.finished_at - report.started_at).total_seconds()
        duration = f"{secs:.1f}s"

    lines: list[str] = []

    # --- Header ---
    lines += [
        "# QA Report",
        "",
        f"**URL:** {report.url}  ",
        f"**Date:** {report.started_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Duration:** {duration}  ",
        f"**Result:** {report.passed}/{report.total} passed ({report.pass_rate:.1f}%)",
        "",
    ]

    # --- AI verdict ---
    if ai_analysis:
        lines += ["## Quality Assessment", "", ai_analysis, ""]

    # --- Flows identified ---
    if report.flows:
        lines += [f"## Flows Identified ({len(report.flows)})", ""]
        for flow in report.flows:
            priority = flow.priority.value if hasattr(flow.priority, "value") else str(flow.priority)
            lines.append(f"- **{flow.name}** `{priority}` — {flow.description}")
        lines.append("")

    # --- Results table ---
    lines += ["## Test Results", ""]
    lines += ["| Test | Status | Duration | Error |"]
    lines += ["|------|--------|----------|-------|"]
    for r in report.results:
        icon = _STATUS_ICON.get(r.status, r.status.value)
        dur = f"{r.duration_ms:.0f} ms" if r.duration_ms else ""
        err = (r.error_message or "").replace("|", "-").replace("\n", " ")[:120]
        lines.append(f"| {r.test_case_name} | {icon} | {dur} | {err} |")
    lines.append("")

    # --- Failure details ---
    failures = [r for r in report.results if r.status in (TestStatus.FAILED, TestStatus.ERROR)]
    if failures:
        lines += ["## Failure Details", ""]
        for result in failures:
            lines += [f"### {result.test_case_name}", ""]

            if result.error_message:
                lines += [f"**Error:** {result.error_message}", ""]

            if result.screenshot_path:
                lines += [f"**Screenshot:** `{result.screenshot_path}`", ""]

            selector = (result.metadata or {}).get("failing_selector")
            if selector:
                lines += [f"**Failing selector:** `{selector}`", ""]

            fix = fix_suggestions.get(result.test_case_id)
            if fix:
                lines += ["**Analysis:**", "", fix, ""]

    # --- Self-healing activity ---
    if report.healing_attempts:
        lines += ["## Self-Healing Activity", ""]
        healed_n = sum(1 for a in report.healing_attempts if a.outcome == "healed")
        refused_n = sum(1 for a in report.healing_attempts if a.outcome == "refused")
        failed_n = sum(1 for a in report.healing_attempts if a.outcome == "failed")
        lines += [
            f"**Summary:** {healed_n} healed  |  {refused_n} refused  |  {failed_n} failed",
            "",
            "| Test | Original selector | New selector | Confidence | Outcome |",
            "|------|-------------------|--------------|:----------:|---------|",
        ]
        for a in report.healing_attempts:
            orig = a.original_selector.replace("|", "-")[:60]
            new = (a.new_selector or "—").replace("|", "-")[:60]
            conf = f"{a.confidence:.0%}" if a.confidence else "—"
            outcome_md = {
                "healed": "**healed**",
                "refused": "refused",
                "failed": "failed",
                "error": "error",
            }.get(a.outcome, a.outcome)
            lines.append(f"| {a.test_case_name} | `{orig}` | `{new}` | {conf} | {outcome_md} |")

        lines.append("")
        for a in report.healing_attempts:
            if a.reasoning:
                lines.append(f"- **{a.test_case_name}** ({a.outcome}): {a.reasoning}")
        lines.append("")

    # --- Footer ---
    lines += [
        "---",
        f"*Generated by qa-agent on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_test_code(result: TestResult) -> str:
    """Read the generated test file source, or return empty string."""
    # test_case_id contains the flow id prefix; try to find the file from metadata
    cmd = (result.metadata or {}).get("cmd", "")
    # cmd looks like: "python -m pytest path/to/test_file.py ..."
    for part in cmd.split():
        if part.endswith(".py") and "test_" in part:
            p = Path(part)
            if p.exists():
                try:
                    return p.read_text(encoding="utf-8")
                except Exception:
                    pass
    return ""


def _build_error_output(result: TestResult) -> str:
    parts = []
    if result.stdout:
        parts.append(result.stdout[-3000:])  # last 3 KB
    if result.stderr:
        parts.append(result.stderr[-1000:])
    return "\n".join(parts).strip()


def _build_flows_summary(report: Report) -> str:
    if not report.results:
        return "(no tests run)"
    lines = []
    result_by_id = {r.test_case_id: r for r in report.results}
    # Match by test_case_name against flow names
    for r in report.results:
        icon = _STATUS_ICON.get(r.status, r.status.value)
        lines.append(f"- {r.test_case_name}: {icon}")
    return "\n".join(lines)


def _build_failures_summary(report: Report) -> str:
    failures = [r for r in report.results if r.status in (TestStatus.FAILED, TestStatus.ERROR)]
    if not failures:
        return "(none)"
    lines = []
    for r in failures:
        err = (r.error_message or "no message")[:200]
        lines.append(f"- **{r.test_case_name}**: {err}")
    return "\n".join(lines)


def _open_report(path: Path) -> None:
    """Open the report file in the default system viewer."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["open", str(path)], check=False)
        else:
            import subprocess
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass  # best-effort
