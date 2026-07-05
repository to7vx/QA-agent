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
from typing import Literal

from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from ..events import RunEvent
from ..keystore import KeyStore
from ..models import TestCase
from ..providers import LLMProvider, ProviderError, create_provider
from ..store import Store


class RunBusyError(Exception):
    """A run is already in progress."""


class RunParams(BaseModel):
    url: str = ""
    provider: str = "anthropic"
    model: str = ""
    headed: bool = False
    heal: bool = True
    mode: Literal["full", "execute"] = "full"
    # execute mode: [{id, name, file_path, description}]
    tests: list[dict] = Field(default_factory=list)
    url_label: str = ""


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
        self.store = Store(self.settings.report_dir / "qa.db")
        try:
            self.store.import_legacy(self.settings.report_dir)
        except Exception:
            pass  # legacy import is best-effort

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

        if params.mode == "execute" and not params.tests:
            raise ValueError("Execute mode needs at least one test.")

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

    def run_single_test(self, tc_id: str) -> str:
        """Execute one library test as a fresh run."""
        tc = self.store.get_test_case(tc_id)
        if tc is None:
            raise ValueError("Test case not found.")
        if not Path(tc["file_path"]).exists():
            raise ValueError(f"Test file is missing on disk: {tc['file_path']}")
        defaults = self.keystore.get_defaults()
        return self.start(RunParams(
            provider=defaults["provider"],
            model=defaults["model"],
            mode="execute",
            tests=[{
                "id": tc["id"],
                "name": tc["name"],
                "file_path": tc["file_path"],
                "description": tc.get("scenario", ""),
            }],
            url_label=tc["url"] or tc["name"],
        ))

    def rerun_failed(self, run_id: str) -> str:
        """Re-execute only the failed/error tests of a finished run."""
        payload = self.get_report(run_id)
        if payload is None or not payload.get("report"):
            raise ValueError("Run not found or has no report yet.")
        report = payload["report"]
        failed_ids = {
            r["test_case_id"]
            for r in report.get("results", [])
            if r.get("status") in ("failed", "error")
        }
        if not failed_ids:
            raise ValueError("This run has no failed tests to re-run.")
        cases = [
            tc for tc in report.get("test_cases", [])
            if tc.get("id") in failed_ids and tc.get("file_path")
            and Path(tc["file_path"]).exists()
        ]
        if not cases:
            raise ValueError(
                "The failed tests' files are no longer on disk — "
                "they were likely overwritten by a newer run."
            )
        meta = payload.get("meta", {})
        return self.start(RunParams(
            provider=meta.get("provider", "anthropic"),
            model=meta.get("model", ""),
            mode="execute",
            tests=[{
                "id": tc["id"],
                "name": tc.get("name", tc["id"]),
                "file_path": tc["file_path"],
                "description": tc.get("description", ""),
            } for tc in cases],
            url_label=report.get("url", ""),
        ))

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
        try:
            if self.store.get_run(run_id) is not None:
                return "finished"
        except Exception:
            pass
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
        try:
            entries = self.store.list_runs()
        except Exception:
            entries = []
        # include the active run even before it is persisted
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
            "url": record.params.url or record.params.url_label,
            "provider": record.provider.name,
            "model": record.provider.model,
            "status": "running",
            "started_at": None,
            "finished_at": None,
            "cancelled": False,
            "total": 0, "passed": 0, "failed": 0, "healed": 0, "pass_rate": 0.0,
        }

    def get_report(self, run_id: str) -> dict | None:
        payload = None
        try:
            payload = self.store.get_run(run_id)
        except Exception:
            payload = None
        if payload is None:
            path = self.settings.report_dir / run_id / "report.json"
            if path.exists():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    payload = None
        if payload is None:
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
            if record.params.mode == "execute":
                test_cases = [
                    TestCase(
                        id=t["id"],
                        flow_id="",
                        name=t.get("name", t["id"]),
                        description=t.get("description", ""),
                        file_path=t["file_path"],
                    )
                    for t in record.params.tests
                ]
                asyncio.run(
                    agent.run_tests(
                        test_cases,
                        heal=record.params.heal,
                        cancel=record.cancel,
                        run_id=record.run_id,
                        url_label=record.params.url_label,
                    )
                )
            else:
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
        finally:
            self._persist_to_store(record)

    def _persist_to_store(self, record: RunRecord) -> None:
        """Copy the freshly written report.json into the DB — best-effort."""
        path = self.settings.report_dir / record.run_id / "report.json"
        if not path.exists():
            return
        try:
            self.store.save_run(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass  # storage must never break a run
