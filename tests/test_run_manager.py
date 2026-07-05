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

    def __init__(self, settings, provider, emit, delay=0.0, fail=False,
                 failing_test_file=None):
        self.settings = settings
        self.provider = provider
        self.emit = emit
        self.delay = delay
        self.fail = fail
        self.failing_test_file = failing_test_file

    def _write_report(self, run_id, url, results, test_cases):
        run_dir = self.settings.report_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.json").write_text(
            json.dumps({
                "meta": {"run_id": run_id, "provider": self.provider.name,
                         "model": self.provider.model, "cancelled": False},
                "report": {"id": run_id, "url": url,
                           "started_at": "2026-07-05T00:00:00+00:00",
                           "finished_at": "2026-07-05T00:01:00+00:00",
                           "results": results, "test_cases": test_cases,
                           "healing_attempts": [], "markdown_path": ""},
            }),
            encoding="utf-8",
        )

    async def run(self, url, heal=True, cancel=None, run_id=None):
        self.emit(RunEvent(type="run_started", data={"run_id": run_id, "url": url}))
        if self.fail:
            raise RuntimeError("agent exploded")
        if self.delay:
            await asyncio.sleep(self.delay)
        results = [{"test_case_id": "t1", "test_case_name": "T1",
                    "status": "passed", "healed": False}]
        test_cases = [{"id": "t1", "name": "T1", "file_path": ""}]
        if self.failing_test_file:
            results.append({"test_case_id": "t2", "test_case_name": "T2",
                            "status": "failed", "healed": False})
            test_cases.append({"id": "t2", "name": "T2",
                               "file_path": str(self.failing_test_file)})
        self._write_report(run_id, url, results, test_cases)
        self.emit(RunEvent(type="run_finished", data={"run_id": run_id}))

    async def run_tests(self, test_cases, heal=True, cancel=None, run_id=None,
                        url_label=""):
        self.emit(RunEvent(
            type="run_started",
            data={"run_id": run_id, "url": url_label, "mode": "execute",
                  "test_count": len(test_cases)},
        ))
        results = [{"test_case_id": tc.id, "test_case_name": tc.name,
                    "status": "passed", "healed": False} for tc in test_cases]
        cases = [{"id": tc.id, "name": tc.name, "file_path": tc.file_path}
                 for tc in test_cases]
        self._write_report(run_id, url_label, results, cases)
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


def test_run_single_test(tmp_path):
    manager = _make_manager(tmp_path)
    test_file = tmp_path / "gen" / "composed_x.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_x(): pass", encoding="utf-8")
    manager.store.add_test_case({
        "id": "tc9", "name": "Single", "scenario": "s", "url": "https://a.test",
        "file_path": str(test_file), "code": "def test_x(): pass",
    })
    run_id = manager.run_single_test("tc9")
    _wait_done(manager, run_id)
    assert manager.status(run_id) == "finished"
    events, _ = manager.events_since(run_id, 0)
    assert events[0].data["mode"] == "execute"


def test_run_single_test_missing(tmp_path):
    manager = _make_manager(tmp_path)
    with pytest.raises(ValueError):
        manager.run_single_test("nope")


def test_rerun_failed(tmp_path):
    failing_file = tmp_path / "gen" / "test_failing.py"
    failing_file.parent.mkdir(parents=True, exist_ok=True)
    failing_file.write_text("def test_f(): pass", encoding="utf-8")
    manager = _make_manager(tmp_path, failing_test_file=failing_file)
    run_id = manager.start(RunParams(url="https://example.com"))
    _wait_done(manager, run_id)

    rerun_id = manager.rerun_failed(run_id)
    _wait_done(manager, rerun_id)
    events, _ = manager.events_since(rerun_id, 0)
    assert events[0].data["mode"] == "execute"
    assert events[0].data["test_count"] == 1  # only the failed test


def test_rerun_failed_nothing_to_rerun(tmp_path):
    manager = _make_manager(tmp_path)  # all tests pass in FakeAgent
    run_id = manager.start(RunParams(url="https://example.com"))
    _wait_done(manager, run_id)
    with pytest.raises(ValueError):
        manager.rerun_failed(run_id)


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
