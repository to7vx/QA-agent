"""Main orchestrator: Explorer -> Generator -> Executor -> Reporter."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from .config import Settings
from .events import EmitFn, RunEvent
from .executor import Executor
from .explorer import Explorer
from .generator import Generator
from .healer import Healer
from .keystore import KeyStore
from .models import Report, TestResult
from .providers import LLMProvider, ProviderError, create_provider
from .reporter import Reporter

console = Console()


def build_default_provider(settings: Settings) -> LLMProvider:
    """Resolve provider + key from settings and the keystore."""
    keystore = KeyStore()
    api_key = keystore.get_key(settings.provider)
    if not api_key:
        raise ProviderError(
            f"No API key configured for provider '{settings.provider}'. "
            "Add one in the dashboard Settings page or set the environment variable."
        )
    return create_provider(settings.provider, settings.model, api_key)


class QAAgent:
    def __init__(
        self,
        settings: Settings,
        provider: LLMProvider | None = None,
        emit: EmitFn | None = None,
    ) -> None:
        self.settings = settings
        self.provider = provider or build_default_provider(settings)
        self.emit: EmitFn = emit or (lambda event: None)
        self.explorer = Explorer(settings, self.provider)
        self.generator = Generator(settings, self.provider)
        self.executor = Executor(settings)
        self.reporter = Reporter(settings.report_dir, provider=self.provider)

    # ------------------------------------------------------------------

    def _event(self, type_: str, **data) -> None:
        self.emit(RunEvent(type=type_, data=data))

    def _cancelled(self, cancel: threading.Event | None) -> bool:
        if cancel is not None and cancel.is_set():
            self._event("cancelled")
            return True
        return False

    # ------------------------------------------------------------------

    async def run(
        self,
        url: str,
        open_report: bool = False,
        heal: bool = True,
        cancel: threading.Event | None = None,
        run_id: str | None = None,
    ) -> Report:
        settings = self.settings
        settings.ensure_dirs()

        report = Report(
            id=run_id or uuid.uuid4().hex[:12],
            url=url,
            started_at=datetime.now(timezone.utc),
        )

        self._event(
            "run_started",
            run_id=report.id,
            url=url,
            provider=self.provider.name,
            model=self.provider.model,
            heal=heal,
        )
        console.print(f"\n[bold cyan]QA Agent[/bold cyan] starting on {url}\n")

        # Step 1: Explore
        self._event("stage", stage="explore")
        console.print("[dim]Step 1/4[/dim]  Exploring page and identifying flows...")
        flows = await self.explorer.explore(url)
        report.flows = flows
        page_context = (
            self.explorer.last_snapshot.to_prompt_context()
            if self.explorer.last_snapshot
            else ""
        )
        self._event(
            "flows_found",
            flows=[f.model_dump(mode="json") for f in flows],
        )
        console.print(f"         Found [bold]{len(flows)}[/bold] flows\n")

        if self._cancelled(cancel):
            return self._finish(report, cancelled=True)

        # Step 2: Generate
        self._event("stage", stage="generate")
        console.print("[dim]Step 2/4[/dim]  Generating test cases...\n")
        test_cases = self.generator.generate(
            flows,
            page_context=page_context,
            on_progress=lambda tc: self._event(
                "test_generated",
                test=tc.model_dump(mode="json", exclude={"playwright_code"}),
            ),
        )
        report.test_cases = test_cases
        console.print(f"\n         Generated [bold]{len(test_cases)}[/bold] test cases\n")

        if self._cancelled(cancel):
            return self._finish(report, cancelled=True)

        # Step 3: Write
        manifest_path = self.generator.write(test_cases, url=url)
        console.print(
            f"         Written to [dim]{settings.output_dir}/[/dim]  "
            f"manifest: [dim]{manifest_path.name}[/dim]\n"
        )

        # Step 4: Execute (with optional self-healing)
        self._event("stage", stage="execute")
        heal_label = "" if not heal else "  [dim](self-healing enabled)[/dim]"
        console.print(f"[dim]Step 4/4[/dim]  Executing tests...{heal_label}\n")

        healer = Healer(settings, self.provider) if heal else None
        results, healing_attempts = self.executor.run(
            test_cases,
            healer=healer,
            url=url,
            on_test=self._on_test,
            cancel=cancel,
        )
        report.results = results
        report.healing_attempts = healing_attempts
        for attempt in healing_attempts:
            self._event("healing", attempt=attempt.model_dump(mode="json"))
        self.executor.save_raw_results(results, healing_attempts)

        if self._cancelled(cancel):
            return self._finish(report, cancelled=True)

        # Finalize report
        self._event("stage", stage="report")
        report = self.reporter.finalize(report, open_after=open_report)
        console.print()
        self.reporter.print_summary(report)

        return self._finish(report)

    # ------------------------------------------------------------------

    async def run_tests(
        self,
        test_cases: list,
        heal: bool = True,
        cancel: threading.Event | None = None,
        run_id: str | None = None,
        url_label: str = "",
    ) -> Report:
        """Execute-only run: skip explore/generate, just run the given tests."""
        settings = self.settings
        settings.ensure_dirs()

        report = Report(
            id=run_id or uuid.uuid4().hex[:12],
            url=url_label or (test_cases[0].name if test_cases else ""),
            started_at=datetime.now(timezone.utc),
        )
        report.test_cases = test_cases

        self._event(
            "run_started",
            run_id=report.id,
            url=report.url,
            provider=self.provider.name,
            model=self.provider.model,
            heal=heal,
            mode="execute",
            test_count=len(test_cases),
        )

        self._event("stage", stage="execute")
        console.print(
            f"\n[bold cyan]QA Agent[/bold cyan] executing {len(test_cases)} test(s)\n"
        )

        healer = Healer(settings, self.provider) if heal else None
        results, healing_attempts = self.executor.run(
            test_cases,
            healer=healer,
            url=url_label,
            on_test=self._on_test,
            cancel=cancel,
        )
        report.results = results
        report.healing_attempts = healing_attempts
        for attempt in healing_attempts:
            self._event("healing", attempt=attempt.model_dump(mode="json"))

        if self._cancelled(cancel):
            return self._finish(report, cancelled=True)

        self._event("stage", stage="report")
        report = self.reporter.finalize(report, open_after=False)
        self.reporter.print_summary(report)
        return self._finish(report)

    # ------------------------------------------------------------------

    def _on_test(self, tc, result: TestResult | None) -> None:
        if result is None:
            self._event("test_started", test_id=tc.id, name=tc.name)
        else:
            self._event("test_result", result=result.model_dump(mode="json"))

    def _finish(self, report: Report, cancelled: bool = False) -> Report:
        if report.finished_at is None:
            report.finished_at = datetime.now(timezone.utc)
        self._persist(report, cancelled=cancelled)
        self._event(
            "run_finished",
            run_id=report.id,
            cancelled=cancelled,
            total=report.total,
            passed=report.passed,
            failed=report.failed,
            pass_rate=report.pass_rate,
            markdown_path=report.markdown_path,
        )
        return report

    def _persist(self, report: Report, cancelled: bool = False) -> Path:
        """Write reports/<run_id>/report.json — the dashboard's data source."""
        run_dir = self.settings.report_dir / report.id
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "meta": {
                "run_id": report.id,
                "provider": self.provider.name,
                "model": self.provider.model,
                "cancelled": cancelled,
            },
            "report": report.model_dump(mode="json"),
        }
        path = run_dir / "report.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path
