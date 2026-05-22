"""Authenticated-flow helpers + the conftest storage-state fixture + profiles API."""

from __future__ import annotations

import json
import os

import httpx
import pytest

from qa_agent.auth import (
    STORAGE_STATE_ENV,
    origin_of,
    storage_state_file,
    subprocess_env,
    validate_origin_match,
)

SAMPLE_STATE = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}


def test_origin_of() -> None:
    assert origin_of("https://app.example.com/login?x=1") == "https://app.example.com"
    assert origin_of("not a url") == ""


def test_validate_origin_match() -> None:
    assert validate_origin_match("https://a.com", "https://a.com/x") is True
    assert validate_origin_match("https://a.com", "https://b.com/x") is False
    assert validate_origin_match("", "https://anything.com") is True  # no scope = any


def test_storage_state_file_lifecycle() -> None:
    with storage_state_file(SAMPLE_STATE) as path:
        assert path is not None
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            assert json.load(f)["cookies"][0]["name"] == "sid"
    # Deleted on exit.
    assert not os.path.exists(path)


def test_storage_state_file_none() -> None:
    with storage_state_file(None) as path:
        assert path is None


def test_subprocess_env() -> None:
    assert subprocess_env(None) is None
    env = subprocess_env("/tmp/state.json")
    assert env is not None
    assert env[STORAGE_STATE_ENV] == "/tmp/state.json"
    # Inherits the parent environment.
    assert "PATH" in env or "Path" in env


def test_conftest_has_storage_state_fixture() -> None:
    # The generated conftest must inject storage_state when the env var is set.
    from qa_agent.generator import _CONFTEST

    assert "browser_context_args" in _CONFTEST
    assert "QA_STORAGE_STATE_PATH" in _CONFTEST
    assert "storage_state" in _CONFTEST


# --- profiles API ----------------------------------------------------------


@pytest.fixture
def app():
    from qa_agent.api.crypto import generate_key
    from qa_agent.api.main import create_app
    from qa_agent.api.settings import ApiSettings

    return create_app(
        ApiSettings(
            database_url="sqlite:///:memory:",
            secret_key=generate_key(),
            auth_disabled=True,
        )
    )


@pytest.fixture
async def client(app):
    from asgi_lifespan import LifespanManager

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_auth_profile_crud(client: httpx.AsyncClient) -> None:
    assert (await client.get("/auth-profiles")).json() == []

    created = await client.post(
        "/auth-profiles",
        json={
            "name": "staging",
            "origin": "https://app.example.com",
            "storage_state": SAMPLE_STATE,
        },
    )
    assert created.status_code == 201
    pid = created.json()["id"]

    listed = (await client.get("/auth-profiles")).json()
    assert len(listed) == 1
    assert listed[0]["name"] == "staging"
    # The encrypted storage_state is never exposed in the listing.
    assert "storage_state" not in listed[0]
    assert "abc" not in json.dumps(listed)

    assert (await client.delete(f"/auth-profiles/{pid}")).status_code == 204
    assert (await client.get("/auth-profiles")).json() == []


async def test_delete_unknown_profile_404(client: httpx.AsyncClient) -> None:
    assert (await client.delete("/auth-profiles/nope")).status_code == 404
