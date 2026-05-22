"""LLM client: retry/backoff behavior and token/cost accounting.

Offline — litellm.completion is monkeypatched; no network, no real keys.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import tenacity.nap

from qa_agent import llm as llm_mod
from qa_agent.config import Settings
from qa_agent.llm import AuthenticationError, LLMClient, RateLimitError
from qa_agent.pricing import estimate_cost, price_for


def _fake_response(content: str = "ok", *, prompt: int = 100, completion: int = 50):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


def _client() -> LLMClient:
    return LLMClient(
        Settings(anthropic_api_key="x", model="anthropic/claude-sonnet-4-6"),
        mutate_env=False,
    )


def test_retries_transient_then_succeeds(monkeypatch) -> None:
    calls = {"n": 0}

    def flaky(*, model, api_key, max_tokens, messages):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RateLimitError("slow down", llm_provider="anthropic", model=model)
        return _fake_response("recovered")

    # Skip tenacity's backoff sleep so the test is fast.
    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_: None)
    monkeypatch.setattr(llm_mod.litellm, "completion", flaky)

    out = _client().complete(system="s", user="u")
    assert out == "recovered"
    assert calls["n"] == 2  # one failure + one success


def test_auth_error_is_not_retried(monkeypatch) -> None:
    calls = {"n": 0}

    def always_auth(*, model, api_key, max_tokens, messages):
        calls["n"] += 1
        raise AuthenticationError("bad key", llm_provider="anthropic", model=model)

    monkeypatch.setattr(llm_mod.litellm, "completion", always_auth)

    with pytest.raises(AuthenticationError):
        _client().complete(system="s", user="u")
    assert calls["n"] == 1  # failed fast, no retry


def test_usage_accumulates_with_cost(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_mod.litellm, "completion", lambda **_: _fake_response(prompt=1000, completion=500)
    )
    client = _client()
    client.complete(system="s", user="u")
    client.complete(system="s", user="u")

    assert client.usage.calls == 2
    assert client.usage.tokens_in == 2000
    assert client.usage.tokens_out == 1000
    # claude-sonnet-4: $3/Mtok in, $15/Mtok out → (2000*3 + 1000*15)/1e6.
    assert client.usage.cost_usd == pytest.approx((2000 * 3 + 1000 * 15) / 1_000_000)


def test_pricing_known_and_unknown() -> None:
    assert price_for("anthropic/claude-sonnet-4-6") == (3.0, 15.0)
    assert price_for("gemini/gemini-2.5-flash") == (0.30, 2.50)
    assert price_for("some/unknown-model") is None
    assert estimate_cost("unknown", 1000, 1000) == 0.0
