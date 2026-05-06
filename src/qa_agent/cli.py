"""CLI entry point: qa-agent <command> [args]"""

from __future__ import annotations

import asyncio

import click
from rich.console import Console

console = Console()


@click.group()
def cli() -> None:
    """Autonomous AI QA agent powered by Claude and Playwright."""


@cli.command()
@click.argument("url")
@click.option("--headless/--headed", default=True, help="Run browser in headless mode.")
@click.option("--model", default=None, help="Claude model override.")
def run(url: str, headless: bool, model: str | None) -> None:
    """Explore URL, generate tests, run them, and produce a report."""
    console.print(f"[bold cyan]qa-agent run[/bold cyan] {url}")
    console.print("[yellow]Wiring up the agent... (logic coming next)[/yellow]")

    # TODO: instantiate QAAgent and call agent.run(url)
    # from .config import get_settings
    # from .agent import QAAgent
    # settings = get_settings()
    # if model:
    #     settings.model = model
    # settings.headless = headless
    # asyncio.run(QAAgent(settings).run(url))
