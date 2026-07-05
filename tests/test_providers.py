"""Tests for the LLM provider abstraction layer."""

from __future__ import annotations

import pytest

from qa_agent.providers import (
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    create_provider,
)
from qa_agent.providers.registry import PROVIDERS


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeAnthropicResponse:
    def __init__(self, text: str):
        self.content = [type("Block", (), {"text": text})()]


class _FakeAnthropicClient:
    def __init__(self, text="hello", raise_exc=None):
        self._text = text
        self._raise = raise_exc
        self.last_kwargs = None

        outer = self

        class _Messages:
            def create(self, **kwargs):
                outer.last_kwargs = kwargs
                if outer._raise:
                    raise outer._raise
                return _FakeAnthropicResponse(outer._text)

        self.messages = _Messages()


class _FakeOpenAIClient:
    def __init__(self, text="hi", raise_exc=None):
        self._text = text
        self._raise = raise_exc
        self.last_kwargs = None
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.last_kwargs = kwargs
                if outer._raise:
                    raise outer._raise
                message = type("Msg", (), {"content": outer._text})()
                choice = type("Choice", (), {"message": message})()
                return type("Resp", (), {"choices": [choice]})()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


class _FakeGoogleClient:
    def __init__(self, text="hey", raise_exc=None):
        self._text = text
        self._raise = raise_exc
        self.last_kwargs = None
        outer = self

        class _Models:
            def generate_content(self, **kwargs):
                outer.last_kwargs = kwargs
                if outer._raise:
                    raise outer._raise
                return type("Resp", (), {"text": outer._text})()

        self.models = _Models()


def _sdk_exc(cls):
    """Instantiate an SDK exception class without its heavyweight __init__."""
    return cls.__new__(cls)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_has_three_providers():
    assert set(PROVIDERS) == {"anthropic", "openai", "google"}
    for info in PROVIDERS.values():
        assert info.default_model in info.models
        assert info.key_env


def test_create_provider_unknown_id():
    with pytest.raises(ProviderError):
        create_provider("nonexistent", "model-x", "key")


def test_create_provider_defaults_model():
    p = create_provider("anthropic", "", "sk-test")
    assert p.model == PROVIDERS["anthropic"].default_model
    assert isinstance(p, LLMProvider)
    assert p.name == "anthropic"


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------

def test_anthropic_complete():
    p = create_provider("anthropic", "claude-sonnet-4-6", "sk-test")
    fake = _FakeAnthropicClient(text="flows!")
    p._client = fake
    result = p.complete("SYSTEM", "PROMPT", max_tokens=1234)
    assert result == "flows!"
    assert fake.last_kwargs["model"] == "claude-sonnet-4-6"
    assert fake.last_kwargs["system"] == "SYSTEM"
    assert fake.last_kwargs["max_tokens"] == 1234
    assert fake.last_kwargs["messages"] == [{"role": "user", "content": "PROMPT"}]


def test_anthropic_auth_error_mapped():
    import anthropic

    p = create_provider("anthropic", "claude-sonnet-4-6", "bad-key")
    p._client = _FakeAnthropicClient(raise_exc=_sdk_exc(anthropic.AuthenticationError))
    with pytest.raises(ProviderAuthError):
        p.complete("s", "p")


def test_anthropic_rate_limit_mapped():
    import anthropic

    p = create_provider("anthropic", "claude-sonnet-4-6", "k")
    p._client = _FakeAnthropicClient(raise_exc=_sdk_exc(anthropic.RateLimitError))
    with pytest.raises(ProviderRateLimitError):
        p.complete("s", "p")


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------

def test_openai_complete():
    p = create_provider("openai", "gpt-5.1", "sk-test")
    fake = _FakeOpenAIClient(text="tests!")
    p._client = fake
    result = p.complete("SYS", "USER", max_tokens=500)
    assert result == "tests!"
    assert fake.last_kwargs["model"] == "gpt-5.1"
    assert fake.last_kwargs["messages"][0] == {"role": "system", "content": "SYS"}
    assert fake.last_kwargs["messages"][1] == {"role": "user", "content": "USER"}


def test_openai_auth_error_mapped():
    import openai

    p = create_provider("openai", "gpt-5.1", "bad")
    p._client = _FakeOpenAIClient(raise_exc=_sdk_exc(openai.AuthenticationError))
    with pytest.raises(ProviderAuthError):
        p.complete("s", "p")


def test_openai_rate_limit_mapped():
    import openai

    p = create_provider("openai", "gpt-5.1", "k")
    p._client = _FakeOpenAIClient(raise_exc=_sdk_exc(openai.RateLimitError))
    with pytest.raises(ProviderRateLimitError):
        p.complete("s", "p")


# ---------------------------------------------------------------------------
# Google adapter
# ---------------------------------------------------------------------------

def test_google_complete():
    p = create_provider("google", "gemini-2.5-pro", "g-key")
    fake = _FakeGoogleClient(text="gemini says")
    p._client = fake
    result = p.complete("SYS", "USER", max_tokens=999)
    assert result == "gemini says"
    assert fake.last_kwargs["model"] == "gemini-2.5-pro"


def test_google_generic_error_mapped():
    p = create_provider("google", "gemini-2.5-pro", "k")
    p._client = _FakeGoogleClient(raise_exc=RuntimeError("boom"))
    with pytest.raises(ProviderError):
        p.complete("s", "p")
