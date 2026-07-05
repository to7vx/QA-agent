"""QAAgent.run_tests: execute-only event sequence and persistence."""

from __future__ import annotations

import asyncio
import json

import pytest

from qa_agent.agent import QAAgent
from qa_agent.config import Settings
from qa_agent.models import TestCase, TestResult, TestStatus

from tests.test_agent_events import FakeExecutor, FakeProvider, FakeReporter


@pytest.fixture
def agent(tmp_path):
    settings = Settings(output_dir=tmp_path / "gen", report_dir=tmp_path / "reports")
    events = []
    a = QAAgent(settings, provider=FakeProvider(), emit=events.append)
    tc = TestCase(id="t1", flow_id="", name="Composed login", description="d")
    result = TestResult(test_case_id="t1", test_case_name="Composed login", status=TestStatus.PASSED)
    a.executor = FakeExecutor([result])
    a.reporter = FakeReporter()
    return a, events, tc


def test_execute_only_sequence(agent):
    a, events, tc = agent
    report = asyncio.run(
        a.run_tests([tc], heal=False, run_id="exec01", url_label="https://x.test")
    )
    types = [e.type for e in events]
    assert types == [
        "run_started",
        "stage",          # execute (no explore/generate)
        "test_started",
        "test_result",
        "stage",          # report
        "run_finished",
    ]
    assert events[0].data["mode"] == "execute"
    assert events[0].data["test_count"] == 1
    assert report.passed == 1
    assert report.url == "https://x.test"


def test_execute_only_persists_report(agent):
    a, _, tc = agent
    asyncio.run(a.run_tests([tc], heal=False, run_id="exec02"))
    path = a.settings.report_dir / "exec02" / "report.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["meta"]["run_id"] == "exec02"
    assert len(payload["report"]["results"]) == 1
