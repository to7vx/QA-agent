"""Main orchestrator: Explorer -> Generator -> Executor -> Reporter."""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from datetime import UTC, datetime

from rich.console import Console

from .auth import storage_state_file
from .config import Settings
from .events import EventEmitter, ProgressHook
from .executor import Executor
from .explorer import Explorer
from .generator import Generator
from .healer import Healer
from .llm import LLMClient
from .models import AuthProfile, Report
from .reporter import Reporter

console = Console()


class QAAgent:
    def __init__(
        self,
        settings: Settings,
        on_event: ProgressHook | None = None,
        *,
        client: LLMClient | None = None,
        run_id: str | None = None,
    ) -> None:
        self.settings = settings
        # The API supplies a per-user LLMClient (BYOK, mutate_env=False); the
        # CLI lets us build the default one.
        self.client = client or LLMClient(settings)
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.emitter = EventEmitter(run_id=self.run_id, sink=on_event)
        self.explorer = Explorer(settings, self.client)
        self.generator = Generator(settings, self.client)
        self.executor = Executor(settings)
        self.reporter = Reporter(settings.report_dir, client=self.client, model=settings.model)

    async def run(
        self,
        url: str,
        open_report: bool = False,
        heal: bool = True,
        auth: AuthProfile | None = None,
        mode: str = "single",
        max_pages: int = 5,
        parallelism: int = 1,
    ) -> Report:
        settings = self.settings
        settings.ensure_dirs()
        emit = self.emitter

        report = Report(
            id=self.run_id,
            url=url,
            started_at=datetime.now(UTC),
        )

        console.print(f"\n[bold cyan]QA Agent[/bold cyan] starting on {url}\n")

        # Authenticated flows: seed in-process contexts with the login session
        # and materialize a temp storage_state file for the test subprocesses.
        # The ExitStack deletes the temp file when the run ends (any path).
        auth_state = auth.storage_state if auth else None
        cleanup = ExitStack()
        state_path = cleanup.enter_context(storage_state_file(auth_state))
        if auth_state:
            self.explorer.storage_state = auth_state
            self.executor.storage_state_path = state_path

        try:
            # Step 1: Explore (single page) or Crawl (many same-origin pages)
            emit.emit("explore", "start", "Exploring page and identifying flows")
            if mode == "crawl":
                console.print(
                    f"[dim]Step 1/4[/dim]  Crawling up to {max_pages} pages from {url}..."
                )
                from .crawler import Crawler

                crawler = Crawler(settings, self.client, storage_state=auth_state)
                flows, _crawled = await crawler.crawl(url, max_pages=max_pages, emitter=emit)
                page_context = ""  # multi-page; flows carry their own context
            else:
                console.print("[dim]Step 1/4[/dim]  Exploring page and identifying flows...")
                flows = await self.explorer.explore(url)
                page_context = (
                    self.explorer.last_snapshot.to_prompt_context()
                    if self.explorer.last_snapshot
                    else ""
                )
            report.flows = flows
            console.print(f"         Found [bold]{len(flows)}[/bold] flows\n")
            emit.emit(
                "explore",
                "end",
                f"Found {len(flows)} flows",
                flow_count=len(flows),
                flows=[{"id": f.id, "name": f.name, "priority": f.priority.value} for f in flows],
            )

            # Step 2: Generate
            console.print("[dim]Step 2/4[/dim]  Generating test cases...\n")
            emit.emit("generate", "start", "Generating test cases", total=len(flows))
            test_cases = self.generator.generate(flows, page_context=page_context, emitter=emit)
            report.test_cases = test_cases
            console.print(f"\n         Generated [bold]{len(test_cases)}[/bold] test cases\n")
            emit.emit(
                "generate",
                "end",
                f"Generated {len(test_cases)} test cases",
                test_count=len(test_cases),
            )

            # Step 3: Write
            console.print("[dim]Step 3/4[/dim]  Writing test files...")
            manifest_path = self.generator.write(test_cases, url=url)
            console.print(
                f"         Written to [dim]{settings.output_dir}/[/dim]  "
                f"manifest: [dim]{manifest_path.name}[/dim]\n"
            )
            emit.emit("write", "end", "Wrote test files", manifest=manifest_path.name)

            # Step 4: Execute (with optional self-healing)
            heal_label = "" if not heal else "  [dim](self-healing enabled)[/dim]"
            console.print(f"[dim]Step 4/4[/dim]  Executing tests...{heal_label}\n")
            emit.emit("execute", "start", "Executing tests", total=len(test_cases), heal=heal)

            healer = Healer(settings, self.client) if heal else None
            if healer is not None and auth_state:
                healer.storage_state = auth_state
                healer.storage_state_path = state_path
            if parallelism > 1:
                results, healing_attempts = self.executor.run_parallel(
                    test_cases,
                    healer=healer,
                    url=url,
                    emitter=emit,
                    max_workers=parallelism,
                )
            else:
                results, healing_attempts = self.executor.run(
                    test_cases, healer=healer, url=url, emitter=emit
                )
            report.results = results
            report.healing_attempts = healing_attempts
            self.executor.save_raw_results(results, healing_attempts)
            emit.emit(
                "execute",
                "end",
                "Execution complete",
                passed=report.passed,
                failed=report.failed,
                total=report.total,
            )

            # Finalize report
            emit.emit("report", "start", "Analyzing results")
            report = self.reporter.finalize(report, open_after=open_report)
            # Snapshot cumulative LLM usage (explore+generate+heal+report calls
            # all funnel through one client). Done last so reporter calls count.
            report.usage = self.client.usage
            console.print()
            self.reporter.print_summary(report)
            emit.emit("report", "end", "Report ready", markdown_path=report.markdown_path)

            emit.emit(
                "done",
                "end",
                "Run complete",
                passed=report.passed,
                failed=report.failed,
                total=report.total,
                pass_rate=report.pass_rate,
                cost_usd=round(report.usage.cost_usd, 4),
                tokens_in=report.usage.tokens_in,
                tokens_out=report.usage.tokens_out,
            )
        except Exception as exc:  # noqa: BLE001 - surface failure as an event then re-raise
            emit.emit("error", "error", str(exc), error_type=type(exc).__name__)
            raise
        finally:
            cleanup.close()  # delete the temp storage_state file

        return report
