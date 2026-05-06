"""Generates Playwright test files from identified flows using Claude."""

from __future__ import annotations

import ast
import dataclasses
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .config import Settings
from .models import Flow, TestCase
from .prompts import GENERATOR_PROMPT, GENERATOR_SYSTEM, REPAIR_PROMPT, REPAIR_SYSTEM

console = Console()

# Written once into generated_tests/ so pytest finds the tests correctly.
_CONFTEST = '''\
"""conftest.py for AI-generated Playwright tests.

pytest-playwright provides browser/context/page fixtures automatically.
asyncio_mode="auto" is set in pyproject.toml — all async tests run without decoration.

Run all generated tests:
    uv run pytest generated_tests/ -v

Run headed (see the browser):
    uv run pytest generated_tests/ -v --headed

Run a single file:
    uv run pytest generated_tests/test_my_flow_abc123.py -v
"""
'''

# Placeholder context used when no live page snapshot is available.
_NO_CONTEXT = "(No page context available — use selectors from the flow steps as-is.)"


@dataclasses.dataclass
class _GenResult:
    """Internal record tracking per-flow generation outcome."""
    test_case: TestCase
    syntax_valid: bool
    repaired: bool = False
    syntax_error: str | None = None


class GeneratorError(Exception):
    """Raised when generation fails for a reason the caller should handle."""


class Generator:
    def __init__(self, settings: Settings, client: anthropic.Anthropic) -> None:
        self.settings = settings
        self.client = client
        self._results: list[_GenResult] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, flows: list[Flow], page_context: str = "") -> list[TestCase]:
        """Generate a TestCase for each flow. Returns all TestCases including
        any that needed syntax repair — callers should check that files are
        written before executing them."""
        if not flows:
            return []

        self._results = []
        ctx = page_context or _NO_CONTEXT

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Generating tests...", total=len(flows))

            for flow in flows:
                progress.update(task, description=f"Generating: [cyan]{flow.name}[/cyan]")
                result = self._generate_one(flow, ctx)
                self._results.append(result)
                if result.repaired:
                    console.print(f"  [yellow]Repaired syntax[/yellow] in {flow.name}")
                elif not result.syntax_valid:
                    console.print(f"  [red]Syntax error remains[/red] in {flow.name} — check before running")
                progress.advance(task)

        return [r.test_case for r in self._results]

    def write(self, test_cases: list[TestCase], url: str = "") -> Path:
        """Write test .py files, conftest.py, and manifest.json.
        Returns the path to manifest.json."""
        out = self.settings.output_dir
        out.mkdir(parents=True, exist_ok=True)

        # conftest.py — always fresh so it tracks any format changes
        (out / "conftest.py").write_text(_CONFTEST, encoding="utf-8")

        for tc in test_cases:
            Path(tc.file_path).write_text(tc.playwright_code, encoding="utf-8")

        manifest_path = out / "manifest.json"
        manifest_path.write_text(
            json.dumps(self._build_manifest(test_cases, url), indent=2),
            encoding="utf-8",
        )
        return manifest_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_one(self, flow: Flow, page_context: str) -> _GenResult:
        code = self._call_claude_generate(flow, page_context)
        code = _strip_fences(code)

        syntax_error = _check_syntax(code)
        repaired = False

        if syntax_error:
            repaired_code = self._call_claude_repair(code, syntax_error)
            repaired_code = _strip_fences(repaired_code)
            second_error = _check_syntax(repaired_code)
            if second_error is None:
                code = repaired_code
                syntax_error = None
                repaired = True
            else:
                # Repair failed — prepend error as a comment so the file is
                # still importable but clearly marked as broken.
                code = (
                    f"# SYNTAX ERROR — repair failed. Original error:\n"
                    f"# {syntax_error}\n\n"
                    + code
                )

        test_id = f"test_{uuid.uuid4().hex[:8]}"
        slug = _slugify(flow.name)
        file_path = self.settings.output_dir / f"test_{slug}_{test_id[5:11]}.py"

        tc = TestCase(
            id=test_id,
            flow_id=flow.id,
            name=flow.name,
            description=flow.description,
            playwright_code=code,
            file_path=str(file_path),
            tags=flow.tags,
        )
        return _GenResult(
            test_case=tc,
            syntax_valid=(syntax_error is None),
            repaired=repaired,
            syntax_error=syntax_error,
        )

    def _call_claude_generate(self, flow: Flow, page_context: str) -> str:
        response = self.client.messages.create(
            model=self.settings.model,
            max_tokens=4_096,
            system=GENERATOR_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": GENERATOR_PROMPT.format(
                        flow_json=flow.model_dump_json(indent=2),
                        page_context=page_context[:6_000],  # cap to stay within budget
                    ),
                }
            ],
        )
        return response.content[0].text.strip()

    def _call_claude_repair(self, code: str, error: str) -> str:
        response = self.client.messages.create(
            model=self.settings.model,
            max_tokens=4_096,
            system=REPAIR_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": REPAIR_PROMPT.format(error=error, code=code),
                }
            ],
        )
        return response.content[0].text.strip()

    def _build_manifest(self, test_cases: list[TestCase], url: str) -> dict:
        result_map = {r.test_case.id: r for r in self._results}
        tests = []
        for tc in test_cases:
            r = result_map.get(tc.id)
            tests.append(
                {
                    "test_id": tc.id,
                    "flow_id": tc.flow_id,
                    "flow_name": tc.name,
                    "file": Path(tc.file_path).name,
                    "tags": tc.tags,
                    "syntax_valid": r.syntax_valid if r else True,
                    "repaired": r.repaired if r else False,
                    "steps_count": 0,  # populated by executor after run
                }
            )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "model": self.settings.model,
            "flows_count": len(test_cases),
            "output_dir": str(self.settings.output_dir),
            "tests": tests,
        }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _check_syntax(code: str) -> str | None:
    """Return an error string if code fails ast.parse(), else None."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as exc:
        return f"SyntaxError at line {exc.lineno}: {exc.msg}"


def _strip_fences(text: str) -> str:
    """Remove markdown code fences Claude occasionally adds."""
    text = re.sub(r"^```(?:python)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:40]
