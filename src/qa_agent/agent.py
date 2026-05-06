"""Main orchestrator: ties Explorer → Generator → Executor → Reporter together."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import anthropic
from rich.console import Console

from .config import Settings
from .executor import Executor
from .explorer import Explorer
from .generator import Generator
from .models import Report
from .reporter import Reporter

console = Console()


class QAAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.explorer = Explorer(settings, self.client)
        self.generator = Generator(settings, self.client)
        self.executor = Executor()
        self.reporter = Reporter(settings.report_dir)

    async def run(self, url: str) -> Report:
        settings = self.settings
        settings.ensure_dirs()

        report = Report(
            id=uuid.uuid4().hex[:12],
            url=url,
            started_at=datetime.now(timezone.utc),
        )

        console.print(f"\n[bold cyan]QA Agent[/bold cyan] starting on [link={url}]{url}[/link]\n")

        console.print("[dim]Step 1/4[/dim]  Exploring page and identifying flows…")
        flows = await self.explorer.explore(url)
        report.flows = flows
        console.print(f"         Found [bold]{len(flows)}[/bold] flows\n")

        console.print("[dim]Step 2/4[/dim]  Generating test cases…")
        test_cases = self.generator.generate(flows)
        report.test_cases = test_cases
        console.print(f"         Generated [bold]{len(test_cases)}[/bold] test cases\n")

        console.print("[dim]Step 3/4[/dim]  Writing test files…")
        self.generator.write(test_cases)
        console.print(f"         Wrote to [dim]{settings.output_dir}/[/dim]\n")

        console.print("[dim]Step 4/4[/dim]  Executing tests…")
        results = self.executor.run(test_cases)
        report.results = results
        console.print()

        report = self.reporter.finalize(report)
        self.reporter.print_summary(report)

        return report
