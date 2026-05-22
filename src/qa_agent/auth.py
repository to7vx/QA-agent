"""Authenticated-flow support: capture and inject Playwright storage state.

A storage state is the cookies + localStorage Playwright needs to start a
browser context already logged in. We capture it once (human logs in), store it
encrypted, and inject it into the explorer, healer, and generated-test browser
contexts so the agent can test pages behind a login.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager, suppress
from typing import Any
from urllib.parse import urlparse

# Env var the generated-test conftest reads to load a storage state.
STORAGE_STATE_ENV = "QA_STORAGE_STATE_PATH"


def origin_of(url: str) -> str:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}"


DEFAULT_CAPTURE_TIMEOUT_S = 300.0


class AuthCaptureTimeout(Exception):
    """Raised when the user doesn't finish logging in within the time limit."""


async def capture_storage_state(
    login_url: str,
    *,
    headless: bool = False,
    timeout_s: float = DEFAULT_CAPTURE_TIMEOUT_S,
) -> dict[str, Any]:
    """Open a browser at ``login_url``, wait for the human to log in, then
    return the captured storage state when the page/window is closed.

    Headed by default — the user needs to interact. Intended for CLI use.
    Raises :class:`AuthCaptureTimeout` if the window isn't closed within
    ``timeout_s`` (default 5 min) so the call can't hang forever.
    """
    from playwright.async_api import TimeoutError as PlaywrightTimeout
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(login_url, wait_until="domcontentloaded")
            # Block until the user closes the page/window, bounded by timeout.
            try:
                await page.wait_for_event("close", timeout=timeout_s * 1000)
            except PlaywrightTimeout as exc:
                raise AuthCaptureTimeout(
                    f"Login not completed within {timeout_s:.0f}s — close the "
                    "browser window after logging in to capture the session."
                ) from exc
            state = await context.storage_state()
        finally:
            with suppress(Exception):
                await browser.close()
        # storage_state() returns a TypedDict; normalize to a plain dict.
        return dict(state)


@contextmanager
def storage_state_file(storage_state: dict[str, Any] | None):
    """Write a storage state to a temp file (0600), yield its path, then delete.

    Yields ``None`` when there's no state, so callers can pass it straight to a
    subprocess env without branching.
    """
    if not storage_state:
        yield None
        return
    fd, path = tempfile.mkstemp(prefix="qa_state_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(storage_state, f)
        with suppress(OSError):  # best-effort on platforms without POSIX perms
            os.chmod(path, 0o600)
        yield path
    finally:
        with suppress(OSError):
            os.remove(path)


def subprocess_env(storage_state_path: str | None) -> dict[str, str] | None:
    """Build a subprocess env that points generated tests at a storage state.

    Returns ``None`` (inherit parent env) when there's no state — keeping the
    CLI's behavior identical.
    """
    if not storage_state_path:
        return None
    env = dict(os.environ)
    env[STORAGE_STATE_ENV] = storage_state_path
    return env


def validate_origin_match(profile_origin: str, target_url: str) -> bool:
    """A profile may only be injected into requests for its own origin."""
    if not profile_origin:
        return True
    return origin_of(target_url) == profile_origin
