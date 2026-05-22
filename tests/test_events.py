"""Tests for the ProgressEvent refactor.

Drives QAAgent.run with fake pipeline stages (no LLM, no browser) and asserts
the structured event stream is well-ordered. Also confirms that omitting a sink
makes emission a no-op (the CLI path).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from qa_agent.events import EventEmitter, ProgressEvent
from qa_agent.models import Usage

from .synthetic import build_report


def test_emitter_noop_without_sink() -> None:
    emitter = EventEmitter(run_id="r1", sink=None)
    assert emitter.enabled is False
    # Must not raise and must not increment observable state.
    emitter.emit("explore", "start", "hi", foo=1)


def test_emitter_stamps_seq_and_run_id() -> None:
    seen: list[ProgressEvent] = []
    emitter = EventEmitter(run_id="r1", sink=seen.append)
    emitter.emit("explore", "start", "a")
    emitter.emit("explore", "end", "b", flow_count=3)

    assert [e.seq for e in seen] == [0, 1]
    assert all(e.run_id == "r1" for e in seen)
    assert seen[1].data["flow_count"] == 3


def test_emitter_swallows_sink_errors() -> None:
    def boom(_ev: ProgressEvent) -> None:
        raise RuntimeError("sink exploded")

    emitter = EventEmitter(run_id="r1", sink=boom)
    # Telemetry failure must never propagate into the pipeline.
    emitter.emit("explore", "start", "a")


def _build_fake_agent(on_event):
    """Construct a QAAgent with every pipeline stage faked out."""
    from qa_agent.agent import QAAgent

    report = build_report("run_fake01")

    class FakeExplorer:
        last_snapshot = None

        async def explore(self, url):
            return report.flows

    class FakeGenerator:
        def generate(self, flows, page_context="", emitter=None):
            if emitter:
                for f in flows:
                    emitter.emit(
                        "generate",
                        "item_done",
                        f.name,
                        flow_id=f.id,
                        syntax_valid=True,
                        repaired=False,
                    )
            return report.test_cases

        def write(self, test_cases, url=""):
            from pathlib import Path

            return Path("manifest.json")

    class FakeExecutor:
        def run(self, test_cases, healer=None, url="", emitter=None):
            if emitter:
                for r in report.results:
                    emitter.emit(
                        "execute", "item_done", r.test_case_name, result_status=r.status.value
                    )
            return report.results, report.healing_attempts

        def save_raw_results(self, results, attempts):
            pass

    class FakeReporter:
        def finalize(self, rep, open_after=False):
            rep.markdown_path = "reports/latest.md"
            return rep

        def print_summary(self, rep):
            pass

    # Bypass __init__ wiring (which would build a real LLMClient).
    agent = QAAgent.__new__(QAAgent)
    from qa_agent.config import Settings

    agent.settings = Settings(anthropic_api_key="x", model="anthropic/claude-sonnet-4-6")
    agent.run_id = "run_fake01"
    agent.emitter = EventEmitter(run_id="run_fake01", sink=on_event)
    # Stand-in for the LLMClient: the agent reads client.usage after finalize.
    agent.client = SimpleNamespace(usage=Usage())
    agent.explorer = FakeExplorer()
    agent.generator = FakeGenerator()
    agent.executor = FakeExecutor()
    agent.reporter = FakeReporter()
    return agent


def test_full_run_event_order(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QA_AGENT_OUTPUT_DIR", str(tmp_path / "gen"))
    monkeypatch.setenv("QA_AGENT_REPORT_DIR", str(tmp_path / "rep"))

    events: list[ProgressEvent] = []
    agent = _build_fake_agent(events.append)
    agent.settings.ensure_dirs()

    report = asyncio.run(agent.run("https://example.com", heal=False))

    phases = [(e.phase, e.status) for e in events]

    # The high-level pipeline phases appear in order.
    assert ("explore", "start") in phases
    assert ("explore", "end") in phases
    assert ("generate", "start") in phases
    assert ("execute", "start") in phases
    assert ("execute", "end") in phases
    assert phases[-1] == ("done", "end")

    # seq is strictly monotonic.
    seqs = [e.seq for e in events]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)

    # The terminal event carries the run summary.
    done = events[-1]
    assert done.data["total"] == report.total
    assert done.data["passed"] == report.passed

    # Per-test item_done events are present for each result.
    item_done = [e for e in events if e.phase == "execute" and e.status == "item_done"]
    assert len(item_done) == len(report.results)


def test_run_emits_error_event_on_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QA_AGENT_OUTPUT_DIR", str(tmp_path / "gen"))
    monkeypatch.setenv("QA_AGENT_REPORT_DIR", str(tmp_path / "rep"))

    events: list[ProgressEvent] = []
    agent = _build_fake_agent(events.append)
    agent.settings.ensure_dirs()

    async def boom(url):
        raise ValueError("explore failed")

    agent.explorer.explore = boom

    import pytest

    with pytest.raises(ValueError):
        asyncio.run(agent.run("https://example.com"))

    assert events[-1].phase == "error"
    assert events[-1].status == "error"
    assert "explore failed" in events[-1].message
