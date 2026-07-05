"""Tests for the dashboard HTTP API."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from qa_agent.config import Settings
from qa_agent.dashboard.api import create_app
from qa_agent.dashboard.run_manager import RunManager
from qa_agent.keystore import KeyStore

from tests.test_run_manager import FakeAgent


@pytest.fixture
def client(tmp_path, monkeypatch):
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    settings = Settings(output_dir=tmp_path / "gen", report_dir=tmp_path / "reports")
    keystore = KeyStore(path=tmp_path / "config.json")

    def factory(settings_, provider, emit):
        return FakeAgent(settings_, provider, emit)

    manager = RunManager(settings=settings, keystore=keystore, agent_factory=factory)
    app = create_app(manager=manager, keystore=keystore, settings=settings)
    return TestClient(app)


def _wait_for_finish(client, run_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = client.get(f"/api/runs/{run_id}").json()
        if payload.get("status") != "running":
            return payload
        time.sleep(0.02)
    raise TimeoutError


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_providers_catalog(client):
    data = client.get("/api/providers").json()
    ids = {p["id"] for p in data}
    assert ids == {"anthropic", "openai", "google"}
    for p in data:
        assert p["configured"] is False
        assert p["masked_key"] is None


def test_key_crud(client):
    r = client.put("/api/settings/keys/openai", json={"api_key": "sk-oai-secret9876"})
    assert r.status_code == 200
    assert r.json()["configured"] is True
    assert r.json()["masked_key"].endswith("9876")
    # full key never appears in any API response
    assert "sk-oai-secret9876" not in r.text

    settings = client.get("/api/settings").json()
    assert settings["providers"]["openai"]["configured"] is True

    r = client.delete("/api/settings/keys/openai")
    assert r.json()["configured"] is False


def test_key_validation(client):
    assert client.put("/api/settings/keys/nope", json={"api_key": "x"}).status_code == 400
    assert client.put("/api/settings/keys/openai", json={"api_key": "  "}).status_code == 400


def test_defaults(client):
    r = client.put("/api/settings/defaults", json={"provider": "google", "model": "gemini-2.5-pro"})
    assert r.json() == {"provider": "google", "model": "gemini-2.5-pro"}


def test_run_requires_key(client):
    r = client.post("/api/runs", json={"url": "https://example.com", "provider": "anthropic"})
    assert r.status_code == 400
    assert "No API key" in r.json()["detail"]


def test_run_requires_valid_url(client):
    client.put("/api/settings/keys/anthropic", json={"api_key": "sk-test-1234"})
    r = client.post("/api/runs", json={"url": "not-a-url", "provider": "anthropic"})
    assert r.status_code == 400


def test_run_lifecycle_and_events(client):
    client.put("/api/settings/keys/anthropic", json={"api_key": "sk-test-1234"})
    r = client.post("/api/runs", json={"url": "https://example.com", "provider": "anthropic"})
    assert r.status_code == 201
    run_id = r.json()["run_id"]

    payload = _wait_for_finish(client, run_id)
    assert payload["status"] == "finished"
    assert payload["meta"]["provider"] == "anthropic"
    assert payload["report"]["url"] == "https://example.com"

    # history shows it
    runs = client.get("/api/runs").json()["runs"]
    assert runs[0]["run_id"] == run_id

    # SSE endpoint replays events for a finished run
    with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
        body = "".join(resp.iter_text())
    assert "run_started" in body
    assert "run_finished" in body
    assert "event: done" in body


def test_get_unknown_run_404(client):
    assert client.get("/api/runs/doesnotexist").status_code == 404
    assert client.get("/api/runs/doesnotexist/events").status_code == 404


def test_cancel_inactive_run_409(client):
    assert client.post("/api/runs/doesnotexist/cancel").status_code == 409


# ---------------------------------------------------------------------------
# v2 endpoints
# ---------------------------------------------------------------------------

def test_insights_empty(client):
    data = client.get("/api/insights").json()
    assert data["kpis"]["runs"] == 0
    assert data["trend"] == []
    assert data["flakiest"] == []


def test_insights_after_run(client):
    client.put("/api/settings/keys/anthropic", json={"api_key": "sk-test-1234"})
    run_id = client.post(
        "/api/runs", json={"url": "https://example.com", "provider": "anthropic"}
    ).json()["run_id"]
    _wait_for_finish(client, run_id)
    data = client.get("/api/insights").json()
    assert data["kpis"]["runs"] == 1
    assert data["trend"][0]["run_id"] == run_id


def test_tests_library_crud(client, tmp_path):
    # empty library
    assert client.get("/api/tests").json() == {"tests": []}
    assert client.get("/api/tests/nope").status_code == 404
    assert client.delete("/api/tests/nope").status_code == 404
    assert client.post("/api/tests/nope/run").status_code in (400, 404)


def test_compose_requires_key(client):
    r = client.post("/api/compose", json={
        "url": "https://example.com", "scenario": "log in and expect a welcome banner",
        "provider": "anthropic",
    })
    assert r.status_code == 400
    assert "No API key" in r.json()["detail"]


def test_compose_validates_input(client):
    client.put("/api/settings/keys/anthropic", json={"api_key": "sk-test-1234"})
    assert client.post("/api/compose", json={
        "url": "ftp://x", "scenario": "long enough scenario", "provider": "anthropic",
    }).status_code == 400
    assert client.post("/api/compose", json={
        "url": "https://x.test", "scenario": "short", "provider": "anthropic",
    }).status_code == 400


def test_compose_success(client, monkeypatch):
    from qa_agent.models import TestCase

    async def fake_compose(provider, url, scenario, settings):
        return TestCase(
            id="composed_ab12cd34", flow_id="", name="log in and expect banner",
            description=scenario, playwright_code="def test(): pass",
            file_path=str(settings.output_dir / "composed_x.py"), tags=["composed"],
        )

    monkeypatch.setattr("qa_agent.dashboard.api.compose_with_snapshot", fake_compose)
    client.put("/api/settings/keys/anthropic", json={"api_key": "sk-test-1234"})
    r = client.post("/api/compose", json={
        "url": "https://example.com",
        "scenario": "log in and expect a welcome banner",
        "provider": "anthropic",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "composed_ab12cd34"
    assert body["code"] == "def test(): pass"
    # now in the library
    tests = client.get("/api/tests").json()["tests"]
    assert tests[0]["id"] == "composed_ab12cd34"
    full = client.get("/api/tests/composed_ab12cd34").json()
    assert full["code"] == "def test(): pass"


def test_rerun_failed_no_failures(client):
    client.put("/api/settings/keys/anthropic", json={"api_key": "sk-test-1234"})
    run_id = client.post(
        "/api/runs", json={"url": "https://example.com", "provider": "anthropic"}
    ).json()["run_id"]
    _wait_for_finish(client, run_id)
    r = client.post(f"/api/runs/{run_id}/rerun-failed")
    assert r.status_code == 409  # FakeAgent's tests all pass


def test_run_code_endpoint_404s(client):
    assert client.get("/api/runs/none/code/none").status_code == 404
