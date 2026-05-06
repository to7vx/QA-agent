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
    """Autonomous AI QA agent powered by Claude and Playwright."""


# ---------------------------------------------------------------------------
# explore
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("url")
@click.option("--headless/--headed", default=True, help="Run browser in headless mode.")
@click.option("--model", default=None, help="Claude model override.")
def explore(url: str, headless: bool, model: str | None) -> None:
    """Discover user flows on a page without generating or running tests."""
    import anthropic
    from pydantic import ValidationError

    from .config import get_settings
    from .explorer import Explorer, ExplorerError

    try:
        settings = get_settings()
    except ValidationError:
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY is not set.\n"
            "Copy [dim].env.example[/dim] to [dim].env[/dim] and add your key."
        )
        raise SystemExit(1)

    if model:
        settings.model = model
    settings.headless = headless

    console.print(f"\n[bold cyan]qa-agent explore[/bold cyan] {url}\n")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    explorer = Explorer(settings, client)

    try:
        flows = asyncio.run(explorer.explore(url))
    except ExplorerError as exc:
        console.print(f"\n[red]Exploration failed:[/red] {exc}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0)

    _print_flows(flows, url)


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("url")
@click.option("--headless/--headed", default=True, help="Run browser in headless mode.")
@click.option("--model", default=None, help="Claude model override.")
@click.option("--out", default=None, help="Output directory (overrides QA_AGENT_OUTPUT_DIR).")
def generate(url: str, headless: bool, model: str | None, out: str | None) -> None:
    """Explore a URL, then generate and save Playwright test files."""
    import anthropic
    from pydantic import ValidationError
    from rich.table import Table
    from rich import box

    from .config import get_settings
    from .explorer import Explorer, ExplorerError
    from .generator import Generator, GeneratorError

    try:
        settings = get_settings()
    except ValidationError:
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY is not set.\n"
            "Copy [dim].env.example[/dim] to [dim].env[/dim] and add your key."
        )
        raise SystemExit(1)

    if model:
        settings.model = model
    if out:
        from pathlib import Path
        settings.output_dir = Path(out)
    settings.headless = headless

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Step 1: Explore
    console.print(f"\n[bold cyan]qa-agent generate[/bold cyan] {url}\n")
    console.print("[dim]Step 1/2[/dim]  Exploring page...")
    explorer = Explorer(settings, client)
    try:
        flows = asyncio.run(explorer.explore(url))
    except ExplorerError as exc:
        console.print(f"\n[red]Exploration failed:[/red] {exc}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0)

    if not flows:
        console.print("[yellow]No flows identified — nothing to generate.[/yellow]")
        raise SystemExit(0)

    page_context = (
        explorer.last_snapshot.to_prompt_context() if explorer.last_snapshot else ""
    )
    console.print(f"  Found [bold]{len(flows)}[/bold] flows\n")

    # Step 2: Generate
    console.print("[dim]Step 2/2[/dim]  Generating test files...\n")
    gen = Generator(settings, client)
    try:
        test_cases = gen.generate(flows, page_context=page_context)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0)

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
            "[green]OK[/green]" if (r and r.syntax_valid) else
            "[yellow]repaired[/yellow]" if (r and r.repaired) else
            "[red]error[/red]"
        )
        table.add_row(fname, tc.name, f"[{pcolor}]{pval}[/{pcolor}]", syntax_str)

    console.print()
    console.print(table)
    console.print(
        f"\n[bold green]{len(test_cases)} test file(s) written[/bold green] "
        f"to [dim]{settings.output_dir}/[/dim]"
    )
    console.print(f"Manifest: [dim]{manifest_path}[/dim]")
    console.print(
        f"\nRun them: [bold]uv run pytest {settings.output_dir}/ -v[/bold]\n"
    )


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--dir", "out_dir", default=None, help="generated_tests/ directory (default: from .env).")
@click.option("--headed", is_flag=True, default=False, help="Run browser in visible window.")
@click.option("--no-heal", "no_heal", is_flag=True, default=False, help="Disable self-healing (useful for debugging).")
def execute(out_dir: str | None, headed: bool, no_heal: bool) -> None:
    """Run whatever tests are in generated_tests/ and show live results."""
    import anthropic as _anthropic
    from pydantic import ValidationError

    from .config import get_settings
    from .executor import Executor
    from .healer import Healer

    try:
        settings = get_settings()
    except ValidationError:
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY is not set.\n"
            "Copy [dim].env.example[/dim] to [dim].env[/dim] and add your key."
        )
        raise SystemExit(1)

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
            client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
            healer = Healer(settings, client, settings.model)
        except Exception:
            console.print("[yellow]Could not initialise healer — running without self-healing.[/yellow]")

    try:
        results, healing_attempts = executor.run(test_cases, healer=healer)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0)

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
        f"of {len(results)} total"
        + (f"  [green]({healed} self-healed)[/green]" if healed else "")
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
@click.option("--model", default=None, help="Claude model override.")
@click.option("--open", "open_report", is_flag=True, default=False, help="Open report in default viewer after run.")
@click.option("--no-heal", "no_heal", is_flag=True, default=False, help="Disable self-healing (useful for debugging).")
def run(url: str, headless: bool, model: str | None, open_report: bool, no_heal: bool) -> None:
    """Full pipeline: explore -> generate -> execute -> report."""
    import anthropic
    from pydantic import ValidationError

    from .config import get_settings
    from .agent import QAAgent

    try:
        settings = get_settings()
    except ValidationError:
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY is not set.\n"
            "Copy [dim].env.example[/dim] to [dim].env[/dim] and add your key."
        )
        raise SystemExit(1)

    if model:
        settings.model = model
    settings.headless = headless

    try:
        report = asyncio.run(
            QAAgent(settings).run(url, open_report=open_report, heal=not no_heal)
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(0)

    raise SystemExit(0 if report.failed == 0 else 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_flows(flows: list, url: str) -> None:
    from .models import FlowPriority

    if not flows:
        console.print("[yellow]No flows identified.[/yellow]")
        return

    console.print(
        f"\n[bold green]{len(flows)} user flow(s) identified[/bold green] on {url}\n"
    )

    for i, flow in enumerate(flows, 1):
        priority_val = flow.priority.value if isinstance(flow.priority, FlowPriority) else str(flow.priority)
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
