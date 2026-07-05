"""QAAgent emits the expected event sequence and persists report.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agent.agent import QAAgent
from qa_agent.config import Settings
from qa_agent.models import Flow, TestCase, TestResult, TestStatus


class FakeProvider:
    name = "anthropic"
    model = "claude-sonnet-4-6"

    def complete(self, system, prompt, max_tokens=4096):
        return "{}"


class FakeExplorer:
    last_snapshot = None

    def __init__(self, flows):
        self._flows = flows

    async def explore(self, url):
        return self._flows


class FakeGenerator:
    def __init__(self, test_cases):
        self._tcs = test_cases

    def generate(self, flows, page_context="", on_progress=None):
        for tc in self._tcs:
            if on_progress:
                on_progress(tc)
        return self._tcs

    def write(self, test_cases, url=""):
        return Path("manifest.json")


class FakeExecutor:
    def __init__(self, results):
        self._results = results

    def run(self, test_cases, healer=None, url="", on_test=None, cancel=None):
        for tc, result in zip(test_cases, self._results):
            if on_test:
                on_test(tc, None)
                on_test(tc, result)
        return self._results, []

    def save_raw_results(self, results, healing_attempts=None):
        return Path("raw.json")


class FakeReporter:
    def finalize(self, report, open_after=False):
        return report

    def print_summary(self, report):
        pass


@pytest.fixture
def agent(tmp_path):
    settings = Settings(
        output_dir=tmp_path / "gen",
        report_dir=tmp_path / "reports",
    )
    events = []
    a = QAAgent(settings, provider=FakeProvider(), emit=events.append)

    flow = Flow(id="f1", name="Login", description="login flow", url="https://x.test")
    tc = TestCase(id="t1", flow_id="f1", name="Login", description="d")
    result = TestResult(test_case_id="t1", test_case_name="Login", status=TestStatus.PASSED)

    a.explorer = FakeExplorer([flow])
    a.generator = FakeGenerator([tc])
    a.executor = FakeExecutor([result])
    a.reporter = FakeReporter()
    return a, events


def test_event_sequence(agent):
    import asyncio

    a, events = agent
    report = asyncio.run(a.run("https://x.test", run_id="testrun01"))

    types = [e.type for e in events]
    assert types == [
        "run_started",
        "stage",           # explore
        "flows_found",
        "stage",           # generate
        "test_generated",
        "stage",           # execute
        "test_started",
        "test_result",
        "stage",           # report
        "run_finished",
    ]
    assert events[0].data["provider"] == "anthropic"
    assert events[0].data["run_id"] == "testrun01"
    assert events[-1].data["passed"] == 1
    assert report.passed == 1


def test_report_json_persisted(agent, tmp_path):
    import asyncio

    a, _ = agent
    asyncio.run(a.run("https://x.test", run_id="testrun02"))

    path = a.settings.report_dir / "testrun02" / "report.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["meta"]["run_id"] == "testrun02"
    assert payload["meta"]["provider"] == "anthropic"
    assert payload["report"]["url"] == "https://x.test"


def test_cancel_before_generate(agent):
    import asyncio
    import threading

    a, events = agent
    cancel = threading.Event()
    cancel.set()
    asyncio.run(a.run("https://x.test", cancel=cancel, run_id="testrun03"))

    types = [e.type for e in events]
    assert "cancelled" in types
    assert "test_result" not in types
    assert types[-1] == "run_finished"
    finished = events[-1]
    assert finished.data["cancelled"] is True
