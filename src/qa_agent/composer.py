"""AI Test Composer: plain-English scenario + URL → runnable Playwright test."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .explorer import capture_snapshot
from .generator import _check_syntax, _slugify, _strip_fences
from .models import TestCase
from .prompts import COMPOSER_PROMPT, COMPOSER_SYSTEM, REPAIR_PROMPT, REPAIR_SYSTEM
from .providers import LLMProvider

_NO_CONTEXT = "(page context unavailable — rely on role/text locators)"


class ComposerError(Exception):
    """The model could not produce a usable test."""


def compose(
    provider: LLMProvider,
    url: str,
    scenario: str,
    settings: Settings,
    page_context: str = "",
) -> TestCase:
    """Generate, validate, and save one test case. Raises ComposerError."""
    code = provider.complete(
        COMPOSER_SYSTEM,
        COMPOSER_PROMPT.format(
            url=url,
            scenario=scenario.strip(),
            page_context=(page_context or _NO_CONTEXT)[:6_000],
        ),
        max_tokens=4_096,
    )
    code = _strip_fences(code)

    error = _check_syntax(code)
    if error:
        code = _strip_fences(
            provider.complete(
                REPAIR_SYSTEM,
                REPAIR_PROMPT.format(error=error, code=code),
                max_tokens=4_096,
            )
        )
        error = _check_syntax(code)
        if error:
            raise ComposerError(f"Generated test still has a syntax error: {error}")

    name = _scenario_name(scenario)
    tc_id = f"composed_{uuid.uuid4().hex[:8]}"
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    file_path = settings.output_dir / f"composed_{_slugify(name)}_{tc_id[-6:]}.py"
    file_path.write_text(code, encoding="utf-8")
    _append_manifest(settings, tc_id, name, file_path, url)

    return TestCase(
        id=tc_id,
        flow_id="",
        name=name,
        description=scenario.strip(),
        playwright_code=code,
        file_path=str(file_path),
        tags=["composed"],
    )


async def compose_with_snapshot(
    provider: LLMProvider,
    url: str,
    scenario: str,
    settings: Settings,
) -> TestCase:
    """Compose with live page context; falls back to no-context on capture failure."""
    page_context = ""
    try:
        snapshot = await capture_snapshot(url, headless=settings.headless)
        page_context = snapshot.to_prompt_context()
    except Exception:
        pass  # page unreachable or browser issue — compose blind
    return compose(provider, url, scenario, settings, page_context=page_context)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scenario_name(scenario: str) -> str:
    first_line = scenario.strip().splitlines()[0].strip()
    return (first_line[:57] + "...") if len(first_line) > 60 else first_line


def _append_manifest(
    settings: Settings, tc_id: str, name: str, file_path: Path, url: str
) -> None:
    """Register the composed test in manifest.json so the executor can load it."""
    manifest_path = settings.output_dir / "manifest.json"
    data: dict = {"tests": []}
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"tests": []}
    data.setdefault("tests", []).append(
        {
            "test_id": tc_id,
            "flow_id": "",
            "flow_name": name,
            "file": file_path.name,
            "tags": ["composed"],
            "syntax_valid": True,
            "repaired": False,
            "steps_count": 0,
            "url": url,
            "composed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
