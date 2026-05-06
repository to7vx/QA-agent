"""Explores a URL and identifies user flows using Playwright + Claude."""

from __future__ import annotations

import dataclasses
import json
import re
import tempfile
import uuid
from pathlib import Path

import anthropic
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .config import Settings
from .models import Flow, FlowPriority
from .prompts import EXPLORER_PROMPT, EXPLORER_SYSTEM

console = Console()

# ---------------------------------------------------------------------------
# JavaScript injected into the page to collect interactive elements.
# Runs in the browser context — must be plain ES5-compatible JS.
# ---------------------------------------------------------------------------
_COLLECT_ELEMENTS_JS = """
() => {
    var MAX_LINKS = 40;
    var MAX_BUTTONS = 30;
    var MAX_INPUTS = 30;
    var results = [];

    function bestSelector(el) {
        if (el.id) return '#' + el.id;
        var name = el.getAttribute('name');
        if (name) return el.tagName.toLowerCase() + '[name="' + name + '"]';
        var aria = el.getAttribute('aria-label');
        if (aria) return el.tagName.toLowerCase() + '[aria-label="' + aria + '"]';
        var cls = Array.prototype.slice.call(el.classList, 0, 2).join('.');
        return el.tagName.toLowerCase() + (cls ? '.' + cls : '');
    }

    function trimText(s, n) {
        s = (s || '').trim();
        return s.length > n ? s.slice(0, n) + '...' : s;
    }

    // Buttons
    var btns = document.querySelectorAll(
        'button, [role="button"], input[type="button"], input[type="submit"], input[type="reset"]'
    );
    Array.prototype.forEach.call(btns, function(el, i) {
        if (i >= MAX_BUTTONS) return;
        var text = trimText(el.textContent || el.value || el.getAttribute('aria-label'), 80);
        if (!text) return;
        results.push({ type: 'button', text: text, selector: bestSelector(el) });
    });

    // Links — deduplicate by href
    var seenHrefs = {};
    var links = document.querySelectorAll('a[href]');
    var linkCount = 0;
    Array.prototype.forEach.call(links, function(el) {
        if (linkCount >= MAX_LINKS) return;
        var href = el.getAttribute('href') || '';
        if (!href || href === '#' || href.indexOf('javascript:') === 0) return;
        if (seenHrefs[href]) return;
        seenHrefs[href] = true;
        var text = trimText(el.textContent, 80);
        results.push({ type: 'link', text: text, href: href.slice(0, 120), selector: bestSelector(el) });
        linkCount++;
    });

    // Form inputs
    var inputs = document.querySelectorAll(
        'input:not([type="hidden"]):not([type="button"]):not([type="submit"]):not([type="reset"]):not([type="image"]), textarea, select'
    );
    Array.prototype.forEach.call(inputs, function(el, i) {
        if (i >= MAX_INPUTS) return;
        var labelText = '';
        if (el.labels && el.labels[0]) labelText = trimText(el.labels[0].textContent, 60);
        if (!labelText) labelText = el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
        results.push({
            type: 'input',
            input_type: el.type || el.tagName.toLowerCase(),
            name: el.name || '',
            placeholder: (el.placeholder || '').slice(0, 60),
            label: labelText.slice(0, 60),
            selector: bestSelector(el)
        });
    });

    // Forms
    var forms = document.querySelectorAll('form');
    Array.prototype.forEach.call(forms, function(el, i) {
        if (i >= 10) return;
        results.push({
            type: 'form',
            action: (el.action || '').slice(0, 120),
            method: el.method || 'get',
            selector: bestSelector(el)
        });
    });

    return results;
}
"""


@dataclasses.dataclass
class PageSnapshot:
    """Everything captured from the browser before calling Claude."""
    title: str
    url: str
    html: str
    screenshot_path: str
    ax_tree_json: str
    interactive_elements: list[dict]

    def to_prompt_context(self) -> str:
        """Serialize snapshot into the text block sent to Claude."""
        elements_block = json.dumps(self.interactive_elements, indent=2)
        # Trim aggressively — we want signal, not full DOM noise
        ax_excerpt = self.ax_tree_json[:3_500]
        html_excerpt = self.html[:12_000]
        return (
            f"Page title: {self.title}\n"
            f"URL: {self.url}\n\n"
            f"### Interactive elements ({len(self.interactive_elements)} found)\n"
            f"{elements_block}\n\n"
            f"### Accessibility tree (truncated)\n"
            f"{ax_excerpt}\n\n"
            f"### HTML source (truncated)\n"
            f"{html_excerpt}"
        )


class ExplorerError(Exception):
    """Raised when exploration fails in a way the caller should handle."""


class Explorer:
    def __init__(self, settings: Settings, client: anthropic.Anthropic) -> None:
        self.settings = settings
        self.client = client
        # Stored after each explore() call so callers can access page context
        # without launching a second browser session.
        self.last_snapshot: PageSnapshot | None = None

    async def explore(self, url: str) -> list[Flow]:
        """Full pipeline: load page → capture → Claude → list[Flow]."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("Launching browser...", total=None)

            try:
                snapshot = await self._capture_snapshot(url, progress, task)
                self.last_snapshot = snapshot
            except PlaywrightTimeout as exc:
                raise ExplorerError(f"Timed out loading {url}") from exc
            except ExplorerError:
                raise
            except Exception as exc:
                raise ExplorerError(f"Browser error on {url}: {exc}") from exc

            progress.update(task, description="Sending page context to Claude...")

            try:
                flows = self._identify_flows(snapshot)
            except anthropic.AuthenticationError as exc:
                raise ExplorerError("Anthropic API key is invalid or missing.") from exc
            except anthropic.RateLimitError as exc:
                raise ExplorerError("Anthropic rate limit hit — wait a moment and retry.") from exc
            except anthropic.APIError as exc:
                raise ExplorerError(f"Claude API error: {exc}") from exc

            progress.update(task, description=f"Done — {len(flows)} flows identified")

        return flows

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _capture_snapshot(
        self, url: str, progress: Progress, task: object
    ) -> PageSnapshot:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.settings.headless)
            try:
                page = await browser.new_page()
                page.set_default_timeout(30_000)

                progress.update(task, description=f"Navigating to {url}...")
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

                # networkidle is best-effort — polling pages (like HN) never reach it
                try:
                    await page.wait_for_load_state("networkidle", timeout=8_000)
                except PlaywrightTimeout:
                    pass

                progress.update(task, description="Capturing title and HTML...")
                title = await page.title()
                html = await page.content()
                resolved_url = page.url

                progress.update(task, description="Taking screenshot...")
                tmp_dir = Path(tempfile.mkdtemp(prefix="qa_agent_"))
                screenshot_path = tmp_dir / "snapshot.png"
                await page.screenshot(path=str(screenshot_path), full_page=False)

                progress.update(task, description="Extracting interactive elements...")
                try:
                    elements: list[dict] = await page.evaluate(_COLLECT_ELEMENTS_JS)
                except Exception:
                    elements = []

                progress.update(task, description="Capturing accessibility tree...")
                try:
                    ax_raw = await page.accessibility.snapshot()
                    ax_tree_json = json.dumps(ax_raw or {}, indent=2)
                except Exception:
                    ax_tree_json = "{}"

            finally:
                await browser.close()

        return PageSnapshot(
            title=title,
            url=resolved_url,
            html=html,
            screenshot_path=str(screenshot_path),
            ax_tree_json=ax_tree_json,
            interactive_elements=elements,
        )

    def _identify_flows(self, snapshot: PageSnapshot) -> list[Flow]:
        context = snapshot.to_prompt_context()
        response = self.client.messages.create(
            model=self.settings.model,
            max_tokens=4_096,
            system=EXPLORER_SYSTEM,
            messages=[
                {"role": "user", "content": EXPLORER_PROMPT.format(context=context)}
            ],
        )
        raw = _strip_fences(response.content[0].text.strip())

        try:
            flows_data: list[dict] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExplorerError(
                f"Claude returned invalid JSON: {exc}\n\nRaw output:\n{raw[:600]}"
            ) from exc

        if not isinstance(flows_data, list):
            raise ExplorerError(
                f"Expected a JSON array from Claude, got {type(flows_data).__name__}"
            )

        flows: list[Flow] = []
        for item in flows_data:
            item.setdefault("id", f"flow_{uuid.uuid4().hex[:8]}")
            item.setdefault("url", snapshot.url)
            # Coerce priority to a valid enum value; default to medium if unrecognised
            raw_priority = str(item.get("priority", "medium")).lower()
            if raw_priority not in FlowPriority._value2member_map_:
                raw_priority = "medium"
            item["priority"] = raw_priority
            try:
                flows.append(Flow(**item))
            except Exception as exc:
                console.print(f"[yellow]  Skipping malformed flow ({exc})[/yellow]")

        return flows


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    """Remove markdown code fences Claude occasionally adds despite instructions."""
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()
