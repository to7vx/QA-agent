"""Generates Playwright test files from identified flows using Claude."""

from __future__ import annotations

import uuid
from pathlib import Path

import anthropic

from .config import Settings
from .models import Flow, TestCase
from .prompts import GENERATE_SYSTEM, GENERATE_USER


class Generator:
    def __init__(self, settings: Settings, client: anthropic.Anthropic) -> None:
        self.settings = settings
        self.client = client

    def generate(self, flows: list[Flow]) -> list[TestCase]:
        """Generate a TestCase (with Playwright code) for each flow."""
        return [self._generate_one(flow) for flow in flows]

    def _generate_one(self, flow: Flow) -> TestCase:
        response = self.client.messages.create(
            model=self.settings.model,
            max_tokens=4096,
            system=GENERATE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": GENERATE_USER.format(
                        flow_json=flow.model_dump_json(indent=2),
                        url=flow.url,
                    ),
                }
            ],
        )
        code = response.content[0].text.strip()
        test_id = f"test_{uuid.uuid4().hex[:8]}"
        file_path = self.settings.output_dir / f"{test_id}_{_slugify(flow.name)}.py"
        return TestCase(
            id=test_id,
            flow_id=flow.id,
            name=flow.name,
            description=flow.description,
            playwright_code=code,
            file_path=str(file_path),
            tags=flow.tags,
        )

    def write(self, test_cases: list[TestCase]) -> None:
        """Write generated test code to disk."""
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        for tc in test_cases:
            Path(tc.file_path).write_text(tc.playwright_code, encoding="utf-8")


def _slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower())[:40]
