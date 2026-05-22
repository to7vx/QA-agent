"""CLI entry point: qa-agent <command> [args]"""

from __future__ import annotations

import asyncio

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

_PRIORITY_STYLE = {
    "high": "red",
    "medium": "yellow",
    "low": "dim",
}


@click.group()
def cli() -> None:
    """Autonomous AI QA agent. Powered by an LLM (Claude or Gemini) + Playwright."""


# ---------------------------------------------------------------------------
# explore
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("url")
@click.option("--headless/--headed", default=True, help="Run browser in headless mode.")
@click.option(
    "--model",
    default=None,
    help="LiteLLM model string, e.g. 'gemini/gemini-2.0-flash' or 'anthropic/claude-sonnet-4-6'.",
)
def explore(url: str, headless: bool, model: str | None) -> None:
    """Discover user flows on a page without generating or running tests."""
    from pydantic import ValidationError

    from .config import get_settings
    from .explorer import Explorer, ExplorerError
    from .llm import LLMClient

    try:
        if model:
            import os

            os.environ["QA_AGENT_MODEL"] = model
        settings = get_settings()
    except ValidationError as exc:
        _print_config_error(exc)
        raise SystemExit(1) from None

    settings.headless = headless
    url = _normalize_url(url)

    console.print(f"\n[bold cyan]qa-agent explore[/bold cyan] {url}\n")

    client = LLMClient(settings)
    explorer = Explorer(settings, client)

    try:
        flows = asyncio.run(explorer.explore(url))
    except ExplorerError as exc:
        console.print(f"\n[red]Exploration failed:[/red] {exc}")
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0) from None

    _print_flows(flows, url)


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("url")
@click.option("--headless/--headed", default=True, help="Run browser in headless mode.")
@click.option(
    "--model",
    default=None,
    help="LiteLLM model string, e.g. 'gemini/gemini-2.0-flash' or 'anthropic/claude-sonnet-4-6'.",
)
@click.option("--out", default=None, help="Output directory (overrides QA_AGENT_OUTPUT_DIR).")
def generate(url: str, headless: bool, model: str | None, out: str | None) -> None:
    """Explore a URL, then generate and save Playwright test files."""
    from pydantic import ValidationError
    from rich import box
    from rich.table import Table

    from .config import get_settings
    from .explorer import Explorer, ExplorerError
    from .generator import Generator
    from .llm import LLMClient

    try:
        if model:
            import os

            os.environ["QA_AGENT_MODEL"] = model
        settings = get_settings()
    except ValidationError as exc:
        _print_config_error(exc)
        raise SystemExit(1) from None

    if out:
        from pathlib import Path

        settings.output_dir = Path(out)
    settings.headless = headless
    url = _normalize_url(url)

    client = LLMClient(settings)

    # Step 1: Explore
    console.print(f"\n[bold cyan]qa-agent generate[/bold cyan] {url}\n")
    console.print("[dim]Step 1/2[/dim]  Exploring page...")
    explorer = Explorer(settings, client)
    try:
        flows = asyncio.run(explorer.explore(url))
    except ExplorerError as exc:
        console.print(f"\n[red]Exploration failed:[/red] {exc}")
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0) from None

    if not flows:
        console.print("[yellow]No flows identified — nothing to generate.[/yellow]")
        raise SystemExit(0)

    page_context = explorer.last_snapshot.to_prompt_context() if explorer.last_snapshot else ""
    console.print(f"  Found [bold]{len(flows)}[/bold] flows\n")

    # Step 2: Generate
    console.print("[dim]Step 2/2[/dim]  Generating test files...\n")
    gen = Generator(settings, client)
    try:
        test_cases = gen.generate(flows, page_context=page_context)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0) from None

    manifest_path = gen.write(test_cases, url=url)

    # Summary table
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold", expand=False)
    table.add_column("Test file", style="cyan")
    table.add_column("Flow", max_width=30)
    table.add_column("Priority", justify="center")
    table.add_column("Syntax", justify="center")

    flow_priority = {f.id: f.priority.value for f in flows}
    result_map = {r.test_case.id: r for r in gen._results}

    for tc in test_cases:
        from pathlib import Path as _Path

        fname = _Path(tc.file_path).name
        pval = flow_priority.get(tc.flow_id, "?")
        pcolor = _PRIORITY_STYLE.get(pval, "white")
        r = result_map.get(tc.id)
        syntax_str = (
            "[green]OK[/green]"
            if (r and r.syntax_valid)
            else "[yellow]repaired[/yellow]"
            if (r and r.repaired)
            else "[red]error[/red]"
        )
        table.add_row(fname, tc.name, f"[{pcolor}]{pval}[/{pcolor}]", syntax_str)

    console.print()
    console.print(table)
    console.print(
        f"\n[bold green]{len(test_cases)} test file(s) written[/bold green] "
        f"to [dim]{settings.output_dir}/[/dim]"
    )
    console.print(f"Manifest: [dim]{manifest_path}[/dim]")
    console.print(f"\nRun them: [bold]uv run pytest {settings.output_dir}/ -v[/bold]\n")


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--dir",
    "out_dir",
    default=None,
    help="generated_tests/ directory (default: from .env).",
)
@click.option("--headed", is_flag=True, default=False, help="Run browser in visible window.")
@click.option(
    "--no-heal",
    "no_heal",
    is_flag=True,
    default=False,
    help="Disable self-healing (useful for debugging).",
)
def execute(out_dir: str | None, headed: bool, no_heal: bool) -> None:
    """Run whatever tests are in generated_tests/ and show live results."""
    from pydantic import ValidationError

    from .config import get_settings
    from .executor import Executor
    from .healer import Healer
    from .llm import LLMClient

    try:
        settings = get_settings()
    except ValidationError as exc:
        _print_config_error(exc)
        raise SystemExit(1) from None

    if out_dir:
        from pathlib import Path

        settings.output_dir = Path(out_dir)

    if headed:
        import os

        os.environ["HEADED"] = "1"

    executor = Executor(settings)
    test_cases = executor.load_from_manifest()

    if not test_cases:
        console.print(
            f"[yellow]No runnable tests found in {settings.output_dir}/[/yellow]\n"
            "Run [bold]qa-agent generate <URL>[/bold] first."
        )
        raise SystemExit(0)

    heal_label = "  [dim](--no-heal)[/dim]" if no_heal else "  [dim](self-healing enabled)[/dim]"
    console.print(
        f"\n[bold cyan]qa-agent execute[/bold cyan]  "
        f"[dim]{len(test_cases)} test(s) from {settings.output_dir}/[/dim]"
        f"{heal_label}\n"
    )

    healer = None
    if not no_heal:
        try:
            client = LLMClient(settings)
            healer = Healer(settings, client)
        except Exception:
            console.print(
                "[yellow]Could not initialise healer — running without self-healing.[/yellow]"
            )

    try:
        results, healing_attempts = executor.run(test_cases, healer=healer)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0) from None

    raw_path = executor.save_raw_results(results, healing_attempts)

    passed = sum(1 for r in results if r.status.value == "passed")
    failed = sum(1 for r in results if r.status.value in ("failed", "error"))
    skipped = sum(1 for r in results if r.status.value == "skipped")
    healed = sum(1 for r in results if r.healed)

    console.print(
        f"\n[bold]Results:[/bold]  "
        f"[green]{passed} passed[/green]  "
        f"[red]{failed} failed[/red]  "
        f"[yellow]{skipped} skipped[/yellow]  "
        f"of {len(results)} total" + (f"  [green]({healed} self-healed)[/green]" if healed else "")
    )
    if healing_attempts:
        refused = sum(1 for a in healing_attempts if a.outcome == "refused")
        heal_failed = sum(1 for a in healing_attempts if a.outcome == "failed")
        console.print(
            f"[bold]Self-healing:[/bold]  "
            f"[green]{healed} healed[/green]  "
            f"[yellow]{refused} refused[/yellow]  "
            f"[red]{heal_failed} failed[/red]"
        )
    console.print(f"Raw results: [dim]{raw_path}[/dim]\n")

    if failed:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# run  (full pipeline)
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("url")
@click.option("--headless/--headed", default=True, help="Run browser in headless mode.")
@click.option(
    "--model",
    default=None,
    help="LiteLLM model string, e.g. 'gemini/gemini-2.0-flash' or 'anthropic/claude-sonnet-4-6'.",
)
@click.option(
    "--open",
    "open_report",
    is_flag=True,
    default=False,
    help="Open report in default viewer after run.",
)
@click.option(
    "--no-heal",
    "no_heal",
    is_flag=True,
    default=False,
    help="Disable self-healing (useful for debugging).",
)
@click.option(
    "--auth-state",
    "auth_state",
    default=None,
    type=click.Path(exists=True),
    help="Path to a Playwright storage_state JSON (from 'qa-agent auth capture') "
    "for authenticated testing.",
)
@click.option(
    "--crawl",
    is_flag=True,
    default=False,
    help="Crawl same-origin pages from the start URL instead of testing a single page.",
)
@click.option(
    "--max-pages",
    "max_pages",
    default=5,
    show_default=True,
    help="Max pages to crawl (with --crawl).",
)
@click.option(
    "--parallel",
    "parallel",
    default=1,
    show_default=True,
    help="Run tests concurrently with N workers.",
)
def run(
    url: str,
    headless: bool,
    model: str | None,
    open_report: bool,
    no_heal: bool,
    auth_state: str | None,
    crawl: bool,
    max_pages: int,
    parallel: int,
) -> None:
    """Full pipeline: explore -> generate -> execute -> report."""
    import json

    from pydantic import ValidationError

    from .agent import QAAgent
    from .auth import origin_of
    from .config import get_settings
    from .models import AuthProfile

    try:
        if model:
            import os

            os.environ["QA_AGENT_MODEL"] = model
        settings = get_settings()
    except ValidationError as exc:
        _print_config_error(exc)
        raise SystemExit(1) from None

    settings.headless = headless
    url = _normalize_url(url)

    auth: AuthProfile | None = None
    if auth_state:
        with open(auth_state, encoding="utf-8") as f:
            state = json.load(f)
        auth = AuthProfile(id="cli", name="cli", origin=origin_of(url), storage_state=state)

    try:
        report = asyncio.run(
            QAAgent(settings).run(
                url,
                open_report=open_report,
                heal=not no_heal,
                auth=auth,
                mode="crawl" if crawl else "single",
                max_pages=max_pages,
                parallelism=parallel,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0) from None

    raise SystemExit(0 if report.failed == 0 else 1)


# ---------------------------------------------------------------------------
# auth  (capture a login session for authenticated testing)
# ---------------------------------------------------------------------------


@cli.group()
def auth() -> None:
    """Manage captured login sessions for authenticated testing."""


@auth.command("capture")
@click.argument("login_url")
@click.option(
    "--out",
    "out_path",
    default="storage_state.json",
    type=click.Path(),
    help="Where to write the captured storage_state JSON.",
)
def auth_capture(login_url: str, out_path: str) -> None:
    """Open a browser at LOGIN_URL, log in by hand, then save the session.

    The captured state can be passed to `qa-agent run <url> --auth-state <file>`.
    """
    import json

    from .auth import capture_storage_state

    login_url = _normalize_url(login_url)
    console.print(f"[cyan]Opening[/cyan] {login_url} — log in, then close the browser window.")
    try:
        state = asyncio.run(capture_storage_state(login_url, headless=False))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0) from None

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    n_cookies = len(state.get("cookies", []))
    console.print(f"[green]Saved[/green] session ({n_cookies} cookies) to [bold]{out_path}[/bold]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_url(url: str) -> str:
    """Prepend https:// if the user passed a bare host like 'demoqa.com'."""
    if "://" not in url:
        return "https://" + url
    return url


def _print_config_error(exc: Exception) -> None:
    console.print(
        f"[red]Config error:[/red] {exc}\n\n"
        "Set the API key matching your QA_AGENT_MODEL:\n"
        "  [dim]ANTHROPIC_API_KEY=...[/dim]   for QA_AGENT_MODEL=anthropic/claude-*\n"
        "  [dim]GEMINI_API_KEY=...[/dim]      for QA_AGENT_MODEL=gemini/gemini-*\n\n"
        "Copy [dim].env.example[/dim] to [dim].env[/dim] and fill it in."
    )


def _print_flows(flows: list, url: str) -> None:
    from .models import FlowPriority

    if not flows:
        console.print("[yellow]No flows identified.[/yellow]")
        return

    console.print(f"\n[bold green]{len(flows)} user flow(s) identified[/bold green] on {url}\n")

    for i, flow in enumerate(flows, 1):
        priority_val = (
            flow.priority.value if isinstance(flow.priority, FlowPriority) else str(flow.priority)
        )
        color = _PRIORITY_STYLE.get(priority_val, "white")

        # Steps table rendered inside the panel
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="bold",
            padding=(0, 1),
            expand=True,
        )
        table.add_column("#", style="dim", width=3, justify="right")
        table.add_column("Step description", min_width=38)
        table.add_column("Action", style="cyan", width=10)
        table.add_column("Expected result", style="dim italic")

        for j, step in enumerate(flow.steps, 1):
            table.add_row(
                str(j),
                step.description,
                step.action or "",
                step.expected_result or "",
            )

        tags_str = "  ".join(f"[dim]{t}[/dim]" for t in flow.tags)
        subtitle = f"[dim]{flow.description}[/dim]"
        if tags_str:
            subtitle += f"\n{tags_str}"

        console.print(
            Panel(
                table,
                title=f"[bold]{i}. {flow.name}[/bold]  [{color}]{priority_val} priority[/{color}]",
                subtitle=subtitle,
                border_style=color,
                padding=(1, 2),
            )
        )
