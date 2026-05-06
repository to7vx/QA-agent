"""Main orchestrator: Explorer -> Generator -> Executor -> Reporter."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import anthropic
from rich.console import Console

from .config import Settings
from .executor import Executor
from .explorer import Explorer
from .generator import Generator
from .healer import Healer
from .models import Report
from .reporter import Reporter

console = Console()


class QAAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.explorer = Explorer(settings, self.client)
        self.generator = Generator(settings, self.client)
        self.executor = Executor(settings)
        self.reporter = Reporter(settings.report_dir, client=self.client, model=settings.model)

    async def run(
        self,
        url: str,
        open_report: bool = False,
        heal: bool = True,
    ) -> Report:
        settings = self.settings
        settings.ensure_dirs()

        report = Report(
            id=uuid.uuid4().hex[:12],
            url=url,
            started_at=datetime.now(timezone.utc),
        )

        console.print(f"\n[bold cyan]QA Agent[/bold cyan] starting on {url}\n")

        # Step 1: Explore
        console.print("[dim]Step 1/4[/dim]  Exploring page and identifying flows...")
        flows = await self.explorer.explore(url)
        report.flows = flows
        page_context = (
            self.explorer.last_snapshot.to_prompt_context()
            if self.explorer.last_snapshot
            else ""
        )
        console.print(f"         Found [bold]{len(flows)}[/bold] flows\n")

        # Step 2: Generate
        console.print("[dim]Step 2/4[/dim]  Generating test cases...\n")
        test_cases = self.generator.generate(flows, page_context=page_context)
        report.test_cases = test_cases
        console.print(f"\n         Generated [bold]{len(test_cases)}[/bold] test cases\n")

        # Step 3: Write
        console.print("[dim]Step 3/4[/dim]  Writing test files...")
        manifest_path = self.generator.write(test_cases, url=url)
        console.print(
            f"         Written to [dim]{settings.output_dir}/[/dim]  "
            f"manifest: [dim]{manifest_path.name}[/dim]\n"
        )

        # Step 4: Execute (with optional self-healing)
        heal_label = "" if not heal else "  [dim](self-healing enabled)[/dim]"
        console.print(f"[dim]Step 4/4[/dim]  Executing tests...{heal_label}\n")

        healer = (
            Healer(settings, self.client, settings.model) if heal else None
        )
        results, healing_attempts = self.executor.run(test_cases, healer=healer, url=url)
        report.results = results
        report.healing_attempts = healing_attempts
        self.executor.save_raw_results(results, healing_attempts)

        # Finalize report
        report = self.reporter.finalize(report, open_after=open_report)
        console.print()
        self.reporter.print_summary(report)

        return report
