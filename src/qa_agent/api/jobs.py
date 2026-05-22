"""Background run execution.

Each run executes on a worker thread (its own asyncio loop, mirroring how the
CLI calls ``asyncio.run``). Pipeline work is blocking (Playwright + pytest
subprocesses), so it must never run on the API event loop.

Per-user concurrency is tracked in-memory; the daily cap is enforced from the
DB by the router before submit.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from ..events import ProgressEvent

if TYPE_CHECKING:
    from ..llm import LLMClient
    from ..store.repository import RunRepository
    from .byok import UserSettingsService
    from .events import EventBus
    from .profiles import AuthProfileService

log = logging.getLogger("qa_agent.api.jobs")


class RunJobManager:
    def __init__(
        self,
        *,
        repo: RunRepository,
        bus: EventBus,
        user_settings: UserSettingsService,
        profiles: AuthProfileService | None = None,
        max_workers: int = 8,
        parallelism: int = 1,
    ) -> None:
        self.repo = repo
        self.bus = bus
        self.user_settings = user_settings
        self.profiles = profiles
        self.parallelism = parallelism
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="qa-run")
        self._active: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    # --- concurrency accounting -------------------------------------------

    def active_count(self, owner_id: str) -> int:
        with self._lock:
            return self._active[owner_id]

    def try_reserve(self, owner_id: str, max_concurrent: int) -> bool:
        """Atomically check the per-user concurrency cap and reserve a slot.

        Returns False (no reservation) when the user is already at the cap. The
        check+increment is under one lock so concurrent requests can't both pass
        the cap. A successful reservation MUST be balanced by a run that ends
        (``_execute`` releases in its finally) or by an explicit ``release``.
        """
        with self._lock:
            if self._active[owner_id] >= max_concurrent:
                return False
            self._active[owner_id] += 1
            return True

    def release(self, owner_id: str) -> None:
        with self._lock:
            self._active[owner_id] = max(0, self._active[owner_id] - 1)

    # --- submission --------------------------------------------------------

    def submit(
        self,
        *,
        run_id: str,
        owner_id: str,
        url: str,
        model: str,
        headless: bool,
        heal: bool,
        auth_profile_id: str | None = None,
        mode: str = "single",
        max_pages: int = 5,
    ):
        """Schedule a reserved run on the worker pool. Caller must have already
        reserved a slot via :meth:`try_reserve`. Returns the Future."""
        return self._pool.submit(
            self._execute,
            run_id,
            owner_id,
            url,
            model,
            headless,
            heal,
            auth_profile_id,
            mode,
            max_pages,
        )

    def _execute(
        self,
        run_id: str,
        owner_id: str,
        url: str,
        model: str,
        headless: bool,
        heal: bool,
        auth_profile_id: str | None = None,
        mode: str = "single",
        max_pages: int = 5,
    ) -> None:
        import asyncio

        from ..agent import QAAgent
        from ..llm import LLMClient

        def hook(event: ProgressEvent) -> None:
            # Persist for replay, then fan out to live SSE subscribers.
            try:
                self.repo.apply_event(run_id=run_id, owner_id=owner_id, event=event)
            except Exception:  # pragma: no cover
                log.exception("Failed to persist event for run %s", run_id)
            self.bus.publish(run_id, _event_payload(event))

        try:
            settings = self.user_settings.build_run_settings(
                owner_id, model=model, headless=headless
            )
            client: LLMClient = LLMClient(settings, mutate_env=False)

            auth = None
            if auth_profile_id and self.profiles is not None:
                auth = self.profiles.load(owner_id, auth_profile_id)

            self.repo.mark_running(run_id=run_id, owner_id=owner_id)

            agent = QAAgent(settings, on_event=hook, client=client, run_id=run_id)
            report = asyncio.run(
                agent.run(
                    url,
                    heal=heal,
                    auth=auth,
                    mode=mode,
                    max_pages=max_pages,
                    parallelism=self.parallelism,
                )
            )

            markdown_body = _read_markdown(report.markdown_path)
            self.repo.finalize_run(owner_id=owner_id, report=report, markdown_body=markdown_body)
        except Exception as exc:  # noqa: BLE001
            log.exception("Run %s failed", run_id)
            self.repo.mark_failed(run_id=run_id, owner_id=owner_id, error=str(exc))
            # Ensure subscribers see a terminal event even if the pipeline
            # raised before emitting its own error event.
            self.bus.publish(
                run_id,
                {
                    "seq": -1,
                    "phase": "error",
                    "status": "error",
                    "message": str(exc),
                    "data": {"error_type": type(exc).__name__},
                },
            )
        finally:
            self.release(owner_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


def _event_payload(event: ProgressEvent) -> dict:
    return {
        "seq": event.seq,
        "ts": event.ts.isoformat(),
        "phase": event.phase,
        "status": event.status,
        "message": event.message,
        "data": event.data,
    }


def _read_markdown(path: str) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
