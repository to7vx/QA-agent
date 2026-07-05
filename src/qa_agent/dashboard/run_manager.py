"""Background run lifecycle: one QA run at a time, with replayable events.

The agent runs in a worker thread under its own asyncio loop (isolated from
uvicorn's), pushing RunEvents into an in-memory list that SSE consumers replay
and tail. Finished runs live on disk as reports/<run_id>/report.json.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from ..config import Settings, get_settings
from ..events import RunEvent
from ..keystore import KeyStore
from ..providers import LLMProvider, ProviderError, create_provider


class RunBusyError(Exception):
    """A run is already in progress."""


class RunParams(BaseModel):
    url: str
    provider: str = "anthropic"
    model: str = ""
    headed: bool = False
    heal: bool = True


@dataclass
class RunRecord:
    run_id: str
    params: RunParams
    provider: LLMProvider
    status: str = "running"  # running | finished | error | cancelled
    events: list[RunEvent] = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class RunManager:
    def __init__(
        self,
        settings: Settings | None = None,
        keystore: KeyStore | None = None,
        agent_factory=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.keystore = keystore or KeyStore()
        self._agent_factory = agent_factory or self._default_agent_factory
        self._lock = threading.Lock()
        self._runs: dict[str, RunRecord] = {}
        self._active_id: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, params: RunParams) -> str:
        api_key = self.keystore.get_key(params.provider)
        if not api_key:
            raise ProviderError(
                f"No API key configured for provider '{params.provider}'. "
                "Add one on the Settings page first."
            )
        provider = create_provider(params.provider, params.model, api_key)

        with self._lock:
            if self._active_id is not None:
                active = self._runs.get(self._active_id)
                if active is not None and active.status == "running":
                    raise RunBusyError("A run is already in progress.")
            run_id = uuid.uuid4().hex[:12]
            record = RunRecord(run_id=run_id, params=params, provider=provider)
            self._runs[run_id] = record
            self._active_id = run_id

        record.thread = threading.Thread(
            target=self._worker, args=(record,), daemon=True
        )
        record.thread.start()
        return run_id

    def cancel(self, run_id: str) -> bool:
        record = self._runs.get(run_id)
        if record is None or record.status != "running":
            return False
        record.cancel.set()
        return True

    def status(self, run_id: str) -> str | None:
        record = self._runs.get(run_id)
        if record is not None:
            return record.status
        if (self.settings.report_dir / run_id / "report.json").exists():
            return "finished"
        return None

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def events_since(self, run_id: str, index: int) -> tuple[list[RunEvent], bool]:
        """Return (events after index, run_is_done)."""
        record = self._runs.get(run_id)
        if record is None:
            # finished run from a previous server session — replay from disk
            return self._events_from_disk(run_id, index), True
        with self._lock:
            new = list(record.events[index:])
            done = record.status != "running"
        return new, done

    def _append(self, record: RunRecord, event: RunEvent) -> None:
        with self._lock:
            record.events.append(event)
        try:
            run_dir = self.settings.report_dir / record.run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            with (run_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(event.model_dump_json() + "\n")
        except OSError:
            pass  # never fail a run over event persistence

    def _events_from_disk(self, run_id: str, index: int) -> list[RunEvent]:
        path = self.settings.report_dir / run_id / "events.jsonl"
        if not path.exists():
            return []
        events: list[RunEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(RunEvent.model_validate_json(line))
            except Exception:
                continue
        return events[index:]

    # ------------------------------------------------------------------
    # History / reports
    # ------------------------------------------------------------------

    def history(self) -> list[dict]:
        entries: list[dict] = []
        report_dir = Path(self.settings.report_dir)
        if not report_dir.exists():
            return entries
        for report_file in report_dir.glob("*/report.json"):
            try:
                payload = json.loads(report_file.read_text(encoding="utf-8"))
                report = payload["report"]
                meta = payload.get("meta", {})
                results = report.get("results", [])
                passed = sum(1 for r in results if r.get("status") == "passed")
                failed = sum(1 for r in results if r.get("status") in ("failed", "error"))
                entries.append({
                    "run_id": meta.get("run_id", report_file.parent.name),
                    "url": report.get("url", ""),
                    "started_at": report.get("started_at"),
                    "finished_at": report.get("finished_at"),
                    "provider": meta.get("provider", ""),
                    "model": meta.get("model", ""),
                    "cancelled": meta.get("cancelled", False),
                    "total": len(results),
                    "passed": passed,
                    "failed": failed,
                    "healed": sum(1 for r in results if r.get("healed")),
                    "pass_rate": (passed / len(results) * 100) if results else 0.0,
                    "status": self.status(meta.get("run_id", report_file.parent.name)),
                })
            except Exception:
                continue  # skip malformed/legacy folders — never crash listing
        entries.sort(key=lambda e: e.get("started_at") or "", reverse=True)
        # include the active run even before its report.json exists
        active = self.active_run()
        if active and not any(e["run_id"] == active["run_id"] for e in entries):
            entries.insert(0, active)
        return entries

    def active_run(self) -> dict | None:
        if self._active_id is None:
            return None
        record = self._runs.get(self._active_id)
        if record is None or record.status != "running":
            return None
        return {
            "run_id": record.run_id,
            "url": record.params.url,
            "provider": record.provider.name,
            "model": record.provider.model,
            "status": "running",
            "started_at": None,
            "finished_at": None,
            "cancelled": False,
            "total": 0, "passed": 0, "failed": 0, "healed": 0, "pass_rate": 0.0,
        }

    def get_report(self, run_id: str) -> dict | None:
        path = self.settings.report_dir / run_id / "report.json"
        if not path.exists():
            record = self._runs.get(run_id)
            if record is not None:
                return {
                    "meta": {
                        "run_id": run_id,
                        "provider": record.provider.name,
                        "model": record.provider.model,
                        "cancelled": False,
                    },
                    "report": None,
                    "status": record.status,
                }
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        payload["status"] = self.status(run_id)
        return payload

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _default_agent_factory(self, settings: Settings, provider: LLMProvider, emit):
        from ..agent import QAAgent

        return QAAgent(settings, provider=provider, emit=emit)

    def _worker(self, record: RunRecord) -> None:
        emit = lambda event: self._append(record, event)
        try:
            settings = self.settings.model_copy()
            settings.provider = record.params.provider
            settings.model = record.provider.model
            settings.headless = not record.params.headed
            agent = self._agent_factory(settings, record.provider, emit)
            asyncio.run(
                agent.run(
                    record.params.url,
                    heal=record.params.heal,
                    cancel=record.cancel,
                    run_id=record.run_id,
                )
            )
            record.status = "cancelled" if record.cancel.is_set() else "finished"
        except Exception as exc:  # surfaced to the UI as run_error
            record.status = "error"
            self._append(
                record,
                RunEvent(type="run_error", data={"message": str(exc)}),
            )
