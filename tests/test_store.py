"""Tests for the SQLite store."""

from __future__ import annotations

import json

import pytest

from qa_agent.store import Store


def _payload(run_id="run1", url="https://a.test", passed=2, failed=1, healed=0,
             provider="anthropic", started="2026-07-06T10:00:00+00:00"):
    results = (
        [{"test_case_id": f"t{i}", "test_case_name": f"Test {i}", "status": "passed",
          "duration_ms": 1000.0, "healed": False, "error_message": None}
         for i in range(passed)]
        + [{"test_case_id": f"f{i}", "test_case_name": f"Flaky {i}", "status": "failed",
            "duration_ms": 2000.0, "healed": False, "error_message": "boom"}
           for i in range(failed)]
    )
    for i in range(healed):
        results[i]["healed"] = True
    total = passed + failed
    return {
        "meta": {"run_id": run_id, "provider": provider, "model": "m1", "cancelled": False},
        "report": {
            "id": run_id,
            "url": url,
            "started_at": started,
            "finished_at": "2026-07-06T10:05:00+00:00",
            "results": results,
            "healing_attempts": [],
            "markdown_path": "reports/x.md",
        },
    }


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "qa.db")


def test_save_and_get_run(store):
    store.save_run(_payload())
    payload = store.get_run("run1")
    assert payload["meta"]["provider"] == "anthropic"
    assert payload["report"]["url"] == "https://a.test"
    assert len(payload["report"]["results"]) == 3


def test_save_run_is_upsert(store):
    store.save_run(_payload())
    store.save_run(_payload(passed=3, failed=0))
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0]["passed"] == 3
    assert runs[0]["failed"] == 0


def test_list_runs_summary_and_order(store):
    store.save_run(_payload("r1", started="2026-07-01T00:00:00+00:00"))
    store.save_run(_payload("r2", started="2026-07-03T00:00:00+00:00"))
    runs = store.list_runs()
    assert [r["run_id"] for r in runs] == ["r2", "r1"]
    r = runs[0]
    assert r["total"] == 3 and r["passed"] == 2 and r["failed"] == 1
    assert r["pass_rate"] == pytest.approx(200 / 3)
    assert r["provider"] == "anthropic"


def test_insights(store):
    store.save_run(_payload("r1", passed=2, failed=1, started="2026-07-01T00:00:00+00:00"))
    store.save_run(_payload("r2", passed=3, failed=0, started="2026-07-02T00:00:00+00:00"))
    store.save_run(_payload("r3", url="https://b.test", passed=0, failed=2,
                            started="2026-07-03T00:00:00+00:00"))
    data = store.insights()
    assert data["kpis"]["runs"] == 3
    assert data["kpis"]["tests_run"] == 8
    assert data["kpis"]["sites"] == 2
    assert len(data["trend"]) == 3
    assert data["trend"][0]["run_id"] == "r1"  # chronological
    # Flaky 0 failed in r1 and r3 -> top flakiest
    assert data["flakiest"][0]["name"] == "Flaky 0"
    assert data["flakiest"][0]["fails"] == 2


def test_test_case_crud(store):
    store.add_test_case({
        "id": "tc1", "name": "Login test", "description": "d", "scenario": "log in",
        "url": "https://a.test", "file_path": "generated_tests/composed_login.py",
        "code": "def test(): pass", "origin": "composed",
        "provider": "openai", "model": "gpt-5.1", "tags": ["auth"],
    })
    listed = store.list_test_cases()
    assert len(listed) == 1
    assert listed[0]["name"] == "Login test"
    assert "code" not in listed[0]
    full = store.get_test_case("tc1")
    assert full["code"] == "def test(): pass"
    assert full["tags"] == ["auth"]
    store.delete_test_case("tc1")
    assert store.list_test_cases() == []
    assert store.get_test_case("tc1") is None


def test_import_legacy(store, tmp_path):
    legacy_dir = tmp_path / "reports" / "legacy1"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "report.json").write_text(
        json.dumps(_payload("legacy1")), encoding="utf-8"
    )
    assert store.import_legacy(tmp_path / "reports") == 1
    assert store.import_legacy(tmp_path / "reports") == 0  # idempotent
    assert store.get_run("legacy1") is not None


def test_healing_kpi(store):
    store.save_run(_payload("r1", passed=2, failed=0, healed=1))
    assert store.insights()["kpis"]["healed"] == 1
