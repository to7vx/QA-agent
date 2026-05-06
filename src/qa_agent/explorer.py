"""Explores a URL and identifies user flows using Playwright + Claude."""

from __future__ import annotations

import json
import uuid

import anthropic
from playwright.async_api import async_playwright

from .config import Settings
from .models import Flow
from .prompts import EXPLORE_SYSTEM, EXPLORE_USER


class Explorer:
    def __init__(self, settings: Settings, client: anthropic.Anthropic) -> None:
        self.settings = settings
        self.client = client

    async def explore(self, url: str) -> list[Flow]:
        """Navigate to *url*, capture a snapshot, and ask Claude to identify flows."""
        snapshot = await self._capture_snapshot(url)
        return await self._identify_flows(url, snapshot)

    async def _capture_snapshot(self, url: str) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.settings.headless)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle")
            content = await page.content()
            await browser.close()
        return content[:20_000]  # trim to avoid token overflow

    async def _identify_flows(self, url: str, snapshot: str) -> list[Flow]:
        response = self.client.messages.create(
            model=self.settings.model,
            max_tokens=4096,
            system=EXPLORE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": EXPLORE_USER.format(url=url, snapshot=snapshot),
                }
            ],
        )
        raw = response.content[0].text.strip()
        flows_data: list[dict] = json.loads(raw)
        return [
            Flow(**{**f, "id": f.get("id") or f"flow_{uuid.uuid4().hex[:8]}"})
            for f in flows_data
        ]
