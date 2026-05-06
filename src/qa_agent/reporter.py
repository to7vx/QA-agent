"""Produces markdown reports from test results."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .models import Report, TestStatus

console = Console()


class Reporter:
    def __init__(self, report_dir: Path) -> None:
        self.report_dir = report_dir

    def finalize(self, report: Report) -> Report:
        report.finished_at = datetime.now(timezone.utc)
        md = self._render_markdown(report)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / f"report_{report.id}.md"
        path.write_text(md, encoding="utf-8")
        report.markdown_path = str(path)
        return report

    def print_summary(self, report: Report) -> None:
        table = Table(title=f"QA Report — {report.url}", show_lines=True)
        table.add_column("Test", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Duration (ms)", justify="right")
        table.add_column("Error")

        for result in report.results:
            status_style = {
                TestStatus.PASSED: "[green]PASSED[/green]",
                TestStatus.FAILED: "[red]FAILED[/red]",
                TestStatus.ERROR: "[red bold]ERROR[/red bold]",
                TestStatus.SKIPPED: "[yellow]SKIPPED[/yellow]",
            }.get(result.status, result.status.value)

            table.add_row(
                result.test_case_name,
                status_style,
                f"{result.duration_ms:.0f}",
                result.error_message or "",
            )

        console.print(table)
        console.print(
            f"\n[bold]Pass rate:[/bold] {report.pass_rate:.1f}%  "
            f"({report.passed}/{report.total})  "
            f"Report: [dim]{report.markdown_path}[/dim]\n"
        )

    def _render_markdown(self, report: Report) -> str:
        duration = ""
        if report.finished_at:
            secs = (report.finished_at - report.started_at).total_seconds()
            duration = f"{secs:.1f}s"

        lines = [
            f"# QA Report",
            f"",
            f"**URL:** {report.url}  ",
            f"**Started:** {report.started_at.isoformat()}  ",
            f"**Duration:** {duration}  ",
            f"**Pass rate:** {report.pass_rate:.1f}% ({report.passed}/{report.total})",
            f"",
            f"## Flows Identified ({len(report.flows)})",
            f"",
        ]
        for flow in report.flows:
            lines += [f"- **{flow.name}** — {flow.description}"]

        lines += [f"", f"## Test Results", f""]
        lines += ["| Test | Status | Duration | Error |", "|------|--------|----------|-------|"]
        for r in report.results:
            err = (r.error_message or "").replace("\n", " ")[:120]
            lines.append(f"| {r.test_case_name} | {r.status.value} | {r.duration_ms:.0f}ms | {err} |")

        return "\n".join(lines) + "\n"
