"""API tests: auth, BYOK, SSRF, tenancy, and a full inline run with a fake pipeline."""

from __future__ import annotations

import httpx
import pytest

from qa_agent.api.security import UnsafeURLError, validate_target_url
from qa_agent.api.settings import ApiSettings

from .synthetic import build_report

# --- SSRF guard (pure unit) ------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://10.0.0.5",
        "http://192.168.1.1",
        "file:///etc/passwd",
        "ftp://example.com",
    ],
)
def test_ssrf_blocks_unsafe(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        validate_target_url(url, resolve_dns=False)


def test_ssrf_allows_public_literal_ip() -> None:
    assert validate_target_url("http://8.8.8.8", resolve_dns=False) == "http://8.8.8.8"


# --- app fixtures ----------------------------------------------------------


@pytest.fixture
def api_settings() -> ApiSettings:
    return ApiSettings(
        database_url="sqlite:///:memory:",
        secret_key="t" * 43 + "=",  # not a valid Fernet key; force ephemeral below
        auth_disabled=True,
        run_inline=True,
        supabase_jwt_secret=None,
    )


@pytest.fixture
def app(monkeypatch, api_settings):
    # Use a real (ephemeral) Fernet key so encryption works.
    from qa_agent.api.crypto import generate_key

    api_settings.secret_key = generate_key()

    # Fake the pipeline so no LLM/browser is touched.
    from qa_agent.events import EventEmitter

    class FakeAgent:
        def __init__(self, settings, on_event=None, *, client=None, run_id=None):
            self.run_id = run_id
            self.emitter = EventEmitter(run_id=run_id, sink=on_event)

        async def run(self, url, open_report=False, heal=True, **kwargs):
            report = build_report(self.run_id)
            report.url = url
            self.emitter.emit("explore", "start", "Exploring")
            self.emitter.emit("explore", "end", "Found flows", flow_count=len(report.flows))
            self.emitter.emit("execute", "start", "Executing", total=len(report.results))
            for r in report.results:
                self.emitter.emit(
                    "execute", "item_done", r.test_case_name, result_status=r.status.value
                )
            self.emitter.emit(
                "done",
                "end",
                "Run complete",
                passed=report.passed,
                failed=report.failed,
                total=report.total,
            )
            return report

    monkeypatch.setattr("qa_agent.agent.QAAgent", FakeAgent)

    from qa_agent.api.main import create_app

    return create_app(api_settings)


@pytest.fixture
async def client(app):
    from asgi_lifespan import LifespanManager

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _set_key(client: httpx.AsyncClient) -> None:
    resp = await client.put("/settings", json={"anthropic_key": "sk-ant-test"})
    assert resp.status_code == 200


# --- tests -----------------------------------------------------------------


async def test_health(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_settings_roundtrip_masks_keys(client: httpx.AsyncClient) -> None:
    before = (await client.get("/settings")).json()
    assert before["has_anthropic_key"] is False

    await _set_key(client)
    after = (await client.get("/settings")).json()
    assert after["has_anthropic_key"] is True
    # The plaintext key is never returned.
    assert "sk-ant-test" not in (await client.get("/settings")).text


async def test_run_without_key_is_422(client: httpx.AsyncClient) -> None:
    resp = await client.post("/runs", json={"url": "https://example.com"})
    assert resp.status_code == 422


async def test_full_run_inline(client: httpx.AsyncClient) -> None:
    await _set_key(client)
    resp = await client.post("/runs", json={"url": "https://example.com", "heal": False})
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    # run_inline => already finished.
    summary = (await client.get(f"/runs/{run_id}")).json()
    assert summary["status"] == "succeeded"
    assert summary["total"] == 3
    assert summary["passed"] == 2

    report = (await client.get(f"/runs/{run_id}/report")).json()
    assert len(report["flows"]) == 3
    assert report["url"] == "https://example.com"

    # Analytics reflect the run.
    analytics = (await client.get("/analytics/summary")).json()
    assert analytics["total_runs"] == 1
    assert analytics["tests_total"] == 3


async def test_unknown_run_is_404(client: httpx.AsyncClient) -> None:
    # Owner-scoped lookup returns nothing → 404 (also the cross-tenant behavior:
    # another user's run id is indistinguishable from a missing one).
    assert (await client.get("/runs/run_does_not_exist")).status_code == 404
    assert (await client.get("/runs/run_does_not_exist/report")).status_code == 404


async def test_ssrf_rejected_at_api(client: httpx.AsyncClient) -> None:
    await _set_key(client)
    resp = await client.post("/runs", json={"url": "http://169.254.169.254"})
    assert resp.status_code == 400


async def test_sse_replays_terminal_event(client: httpx.AsyncClient) -> None:
    await _set_key(client)
    run_id = (
        await client.post("/runs", json={"url": "https://example.com", "heal": False})
    ).json()["run_id"]

    # The run already finished (inline); SSE should replay events incl. terminal.
    async with client.stream("GET", f"/runs/{run_id}/events") as resp:
        assert resp.status_code == 200
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk
            if "done" in body or '"phase": "done"' in body:
                break
    assert "explore" in body
    assert "done" in body
