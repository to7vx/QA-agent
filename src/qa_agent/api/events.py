"""In-process pub/sub bus bridging the worker thread to SSE subscribers.

The pipeline runs on a worker thread (its own event loop). SSE subscribers live
on the main API event loop. ``publish`` is called from the worker thread and
hands delivery back to the API loop via ``call_soon_threadsafe``.

Single-process only. To scale horizontally, swap this for Postgres
LISTEN/NOTIFY behind the same ``subscribe``/``publish`` interface.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the API event loop (called from the FastAPI lifespan)."""
        self._loop = loop

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers[run_id].add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(run_id)
        if subs:
            subs.discard(q)
            if not subs:
                self._subscribers.pop(run_id, None)

    def publish(self, run_id: str, payload: dict[str, Any]) -> None:
        """Thread-safe publish — safe to call from the worker thread."""
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._deliver, run_id, payload)

    def _deliver(self, run_id: str, payload: dict[str, Any]) -> None:
        for q in list(self._subscribers.get(run_id, ())):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow consumer — drop oldest to keep the stream live.
                try:
                    q.get_nowait()
                    q.put_nowait(payload)
                except Exception:
                    pass
