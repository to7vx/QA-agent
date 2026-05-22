"""Persistence + multi-tenancy tests against in-memory SQLite."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from qa_agent.models import TestStatus
from qa_agent.store import RunRepository, make_database

from .synthetic import build_report

USER_A = "00000000-0000-0000-0000-00000000000a"
USER_B = "00000000-0000-0000-0000-00000000000b"


@dataclass
class FakeEvent:
    seq: int
    phase: str
    status: str
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))


@pytest.fixture
def repo() -> RunRepository:
    db = make_database("sqlite://")
    db.create_all()
    return RunRepository(db)


def _seed_run(repo: RunRepository, owner: str, run_id: str) -> None:
    report = build_report(run_id)
    repo.create_run(
        run_id=run_id, owner_id=owner, url=report.url, model="anthropic/claude-sonnet-4-6"
    )
    repo.mark_running(run_id=run_id, owner_id=owner)
    repo.finalize_run(
        owner_id=owner, report=report, markdown_body="# Report", ai_analysis="Healthy."
    )


def test_finalize_and_roundtrip(repo: RunRepository) -> None:
    _seed_run(repo, USER_A, "run_a1")
    report = repo.get_report(run_id="run_a1", owner_id=USER_A)

    assert report is not None
    assert report.url.endswith("saucedemo.com")
    assert len(report.flows) == 3
    assert len(report.test_cases) == 3
    assert report.total == 3
    assert report.passed == 2
    assert report.failed == 1

    # Healing round-trips and is attached to the healed result.
    healed = next(r for r in report.results if r.test_case_id == "tc_flow_checkout")
    assert healed.healed is True
    assert healed.healing is not None
    assert healed.healing.outcome == "healed"
    assert healed.healing.confidence == pytest.approx(0.92)

    failed = next(r for r in report.results if r.status == TestStatus.FAILED)
    assert "9.99" in (failed.error_message or "")


def test_run_summary_counts(repo: RunRepository) -> None:
    _seed_run(repo, USER_A, "run_a1")
    row = repo.get_run_row(run_id="run_a1", owner_id=USER_A)
    assert row is not None
    assert row["status"] == "succeeded"
    assert row["passed"] == 2
    assert row["pass_rate"] == pytest.approx(66.666, abs=0.1)


def test_tenant_isolation(repo: RunRepository) -> None:
    _seed_run(repo, USER_A, "run_a1")

    # User B cannot read user A's run by any path.
    assert repo.get_report(run_id="run_a1", owner_id=USER_B) is None
    assert repo.get_run_row(run_id="run_a1", owner_id=USER_B) is None
    assert repo.list_runs(owner_id=USER_B) == []

    # And finalize for the wrong owner is refused.
    with pytest.raises(PermissionError):
        repo.finalize_run(owner_id=USER_B, report=build_report("run_a1"))


def test_list_runs_scoped(repo: RunRepository) -> None:
    _seed_run(repo, USER_A, "run_a1")
    _seed_run(repo, USER_A, "run_a2")
    _seed_run(repo, USER_B, "run_b1")

    a_runs = repo.list_runs(owner_id=USER_A)
    b_runs = repo.list_runs(owner_id=USER_B)
    assert {r["id"] for r in a_runs} == {"run_a1", "run_a2"}
    assert {r["id"] for r in b_runs} == {"run_b1"}


def test_events_replay_scoped(repo: RunRepository) -> None:
    repo.create_run(run_id="run_a1", owner_id=USER_A, url="https://x.com", model="m")
    for i, (phase, status) in enumerate(
        [("explore", "start"), ("explore", "end"), ("done", "end")]
    ):
        repo.apply_event(
            run_id="run_a1",
            owner_id=USER_A,
            event=FakeEvent(seq=i, phase=phase, status=status, message=phase),
        )

    events = repo.get_events_since(run_id="run_a1", owner_id=USER_A)
    assert [e["seq"] for e in events] == [0, 1, 2]
    assert events[0]["phase"] == "explore"

    # Tenant isolation on the event stream too.
    assert repo.get_events_since(run_id="run_a1", owner_id=USER_B) == []

    # after_seq filters the replay.
    tail = repo.get_events_since(run_id="run_a1", owner_id=USER_A, after_seq=1)
    assert [e["seq"] for e in tail] == [2]


def test_analytics(repo: RunRepository) -> None:
    _seed_run(repo, USER_A, "run_a1")
    _seed_run(repo, USER_A, "run_a2")

    summary = repo.summary(owner_id=USER_A)
    assert summary["total_runs"] == 2
    assert summary["tests_total"] == 6  # 3 per run
    assert summary["tests_passed"] == 4
    assert summary["successful_heals"] == 2

    trend = repo.pass_rate_trend(owner_id=USER_A)
    assert len(trend) == 2
    assert all("pass_rate" in p for p in trend)

    heals = repo.healing_stats(owner_id=USER_A)
    assert heals.get("healed") == 2

    # Other tenant sees nothing.
    assert repo.summary(owner_id=USER_B)["total_runs"] == 0
