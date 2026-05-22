"""Multi-page crawl: discover same-origin pages from a start URL and identify
flows on each, reusing the Explorer's capture + flow-identification.

Link discovery and URL normalization are pure functions (unit-tested without a
browser). The crawl itself drives many pages through a single shared browser
context so an authenticated session is reused across the whole site.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

from playwright.async_api import async_playwright

from .config import Settings
from .events import NULL_EMITTER, EventEmitter
from .explorer import Explorer
from .llm import LLMClient
from .models import Flow


@dataclass
class CrawledPage:
    url: str
    title: str = ""
    depth: int = 0
    discovered_from: str | None = None
    flows: list[Flow] = field(default_factory=list)


# --- pure helpers ----------------------------------------------------------


def normalize_url(url: str, base: str | None = None) -> str:
    """Resolve relative URLs against ``base`` and strip fragments."""
    if base:
        url = urljoin(base, url)
    url, _frag = urldefrag(url)
    # Drop trailing slash (treat /a and /a/ as the same page) except for root.
    p = urlparse(url)
    if p.path.endswith("/") and p.path != "/":
        url = url[:-1]
    return url


def same_origin(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def extract_links(
    elements: list[dict], base_url: str, *, restrict_same_origin: bool = True
) -> list[str]:
    """Pull normalized, deduped page links from captured interactive elements."""
    seen: set[str] = set()
    out: list[str] = []
    for el in elements:
        if el.get("type") != "link":
            continue
        href = el.get("href") or el.get("selector")
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        resolved = normalize_url(href, base_url)
        if urlparse(resolved).scheme not in ("http", "https"):
            continue
        if restrict_same_origin and not same_origin(resolved, base_url):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def _unique_flow_id(flow_id: str, seen: set[str]) -> str:
    """Return a flow id unique within ``seen``, registering it. The LLM reuses
    ids like ``flow_reg01`` across pages; we suffix collisions (``flow_reg01_2``)."""
    candidate = flow_id or "flow"
    if candidate in seen:
        n = 2
        while f"{candidate}_{n}" in seen:
            n += 1
        candidate = f"{candidate}_{n}"
    seen.add(candidate)
    return candidate


class _NullProgress:
    """No-op stand-in for Rich Progress so we can reuse Explorer._capture_from_page."""

    def update(self, *args, **kwargs) -> None:  # noqa: D401
        pass


# --- crawler ---------------------------------------------------------------


class Crawler:
    def __init__(
        self,
        settings: Settings,
        client: LLMClient,
        *,
        storage_state: dict | None = None,
    ) -> None:
        self.settings = settings
        self.explorer = Explorer(settings, client)
        self.explorer.storage_state = storage_state

    async def crawl(
        self,
        start_url: str,
        *,
        max_pages: int = 5,
        restrict_same_origin: bool = True,
        emitter: EventEmitter | None = None,
    ) -> tuple[list[Flow], list[CrawledPage]]:
        emit = emitter or NULL_EMITTER
        start_url = normalize_url(start_url)
        queue: deque[tuple[str, int, str | None]] = deque([(start_url, 0, None)])
        visited: set[str] = set()
        pages: list[CrawledPage] = []
        all_flows: list[Flow] = []
        # Flow ids come from the LLM per page and collide across pages; flows
        # are keyed (id, run_id), so ids must be unique within a single crawl.
        seen_flow_ids: set[str] = set()
        progress, task = _NullProgress(), object()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.settings.headless)
            context = await browser.new_context(storage_state=self.explorer.storage_state or None)
            try:
                while queue and len(visited) < max_pages:
                    url, depth, parent = queue.popleft()
                    if url in visited:
                        continue
                    visited.add(url)

                    emit.emit(
                        "explore",
                        "progress",
                        f"Crawling {url}",
                        url=url,
                        depth=depth,
                        visited=len(visited),
                    )
                    page = await context.new_page()
                    page.set_default_timeout(30_000)
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                        snapshot = await self.explorer._capture_from_page(page, url, progress, task)
                    except Exception:
                        await page.close()
                        continue

                    flows = self.explorer._identify_flows(snapshot)
                    for f in flows:
                        f.tags = [*f.tags, f"page:{url}"]
                        f.id = _unique_flow_id(f.id, seen_flow_ids)
                    all_flows.extend(flows)
                    pages.append(
                        CrawledPage(
                            url=url,
                            title=snapshot.title,
                            depth=depth,
                            discovered_from=parent,
                            flows=flows,
                        )
                    )

                    # Enqueue newly-discovered same-origin links.
                    for link in extract_links(
                        snapshot.interactive_elements,
                        url,
                        restrict_same_origin=restrict_same_origin,
                    ):
                        if link not in visited:
                            queue.append((link, depth + 1, url))

                    await page.close()
            finally:
                await browser.close()

        emit.emit(
            "explore",
            "end",
            f"Crawled {len(pages)} pages, {len(all_flows)} flows",
            page_count=len(pages),
            flow_count=len(all_flows),
        )
        return all_flows, pages
