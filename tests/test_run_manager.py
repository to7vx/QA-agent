"""Tests for the dashboard run manager."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from qa_agent.config import Settings
from qa_agent.dashboard.run_manager import RunBusyError, RunManager, RunParams
from qa_agent.events import RunEvent
from qa_agent.keystore import KeyStore
from qa_agent.providers import ProviderError


class FakeAgent:
    """Stands in for QAAgent: emits events and writes report.json."""

    def __init__(self, settings, provider, emit, delay=0.0, fail=False):
        self.settings = settings
        self.provider = provider
        self.emit = emit
        self.delay = delay
        self.fail = fail

    async def run(self, url, heal=True, cancel=None, run_id=None):
        self.emit(RunEvent(type="run_started", data={"run_id": run_id, "url": url}))
        if self.fail:
            raise RuntimeError("agent exploded")
        if self.delay:
            await asyncio.sleep(self.delay)
        run_dir = self.settings.report_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.json").write_text(
            json.dumps({
                "meta": {"run_id": run_id, "provider": self.provider.name,
                         "model": self.provider.model, "cancelled": False},
                "report": {"id": run_id, "url": url, "started_at": "2026-07-05T00:00:00Z",
                           "finished_at": "2026-07-05T00:01:00Z",
                           "results": [{"status": "passed", "healed": False}]},
            }),
            encoding="utf-8",
        )
        self.emit(RunEvent(type="run_finished", data={"run_id": run_id}))


def _make_manager(tmp_path, **agent_kwargs):
    settings = Settings(output_dir=tmp_path / "gen", report_dir=tmp_path / "reports")
    keystore = KeyStore(path=tmp_path / "config.json")
    keystore.set_key("anthropic", "sk-test-key-1234")

    def factory(settings_, provider, emit):
        return FakeAgent(settings_, provider, emit, **agent_kwargs)

    return RunManager(settings=settings, keystore=keystore, agent_factory=factory)


def _wait_done(manager, run_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if manager.status(run_id) != "running":
            return
        time.sleep(0.02)
    raise TimeoutError("run did not finish")


def test_start_and_finish(tmp_path):
    manager = _make_manager(tmp_path)
    run_id = manager.start(RunParams(url="https://example.com", provider="anthropic"))
    _wait_done(manager, run_id)
    assert manager.status(run_id) == "finished"
    events, done = manager.events_since(run_id, 0)
    assert done
    assert [e.type for e in events] == ["run_started", "run_finished"]


def test_no_key_raises(tmp_path, monkeypatch):
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    settings = Settings(output_dir=tmp_path / "g", report_dir=tmp_path / "r")
    manager = RunManager(settings=settings, keystore=KeyStore(path=tmp_path / "c.json"))
    with pytest.raises(ProviderError):
        manager.start(RunParams(url="https://example.com", provider="openai"))


def test_second_run_busy(tmp_path):
    manager = _make_manager(tmp_path, delay=1.0)
    run_id = manager.start(RunParams(url="https://example.com"))
    with pytest.raises(RunBusyError):
        manager.start(RunParams(url="https://other.com"))
    _wait_done(manager, run_id)
    # after finish, a new run is allowed
    manager.start(RunParams(url="https://other.com"))


def test_agent_error_becomes_run_error_event(tmp_path):
    manager = _make_manager(tmp_path, fail=True)
    run_id = manager.start(RunParams(url="https://example.com"))
    _wait_done(manager, run_id)
    assert manager.status(run_id) == "error"
    events, done = manager.events_since(run_id, 0)
    assert done
    assert events[-1].type == "run_error"
    assert "exploded" in events[-1].data["message"]


def test_history_reads_reports(tmp_path):
    manager = _make_manager(tmp_path)
    run_id = manager.start(RunParams(url="https://example.com"))
    _wait_done(manager, run_id)
    history = manager.history()
    assert len(history) == 1
    entry = history[0]
    assert entry["run_id"] == run_id
    assert entry["total"] == 1
    assert entry["passed"] == 1
    assert entry["pass_rate"] == 100.0


def test_events_replay_from_disk(tmp_path):
    manager = _make_manager(tmp_path)
    run_id = manager.start(RunParams(url="https://example.com"))
    _wait_done(manager, run_id)
    # simulate a fresh server session: new manager, same report dir
    fresh = RunManager(
        settings=manager.settings, keystore=manager.keystore,
        agent_factory=manager._agent_factory,
    )
    events, done = fresh.events_since(run_id, 0)
    assert done
    assert [e.type for e in events] == ["run_started", "run_finished"]
