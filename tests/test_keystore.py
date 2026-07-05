"""Tests for the local API key store."""

from __future__ import annotations

import json

import pytest

from qa_agent.keystore import KeyStore


@pytest.fixture
def store(tmp_path):
    return KeyStore(path=tmp_path / "config.json")


def test_get_key_missing_returns_none(store, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert store.get_key("openai") is None


def test_set_and_get_key(store):
    store.set_key("anthropic", "sk-ant-abc123xyz9")
    assert store.get_key("anthropic") == "sk-ant-abc123xyz9"


def test_key_persists_to_disk(tmp_path):
    path = tmp_path / "config.json"
    KeyStore(path=path).set_key("openai", "sk-oai-secret1234")
    assert KeyStore(path=path).get_key("openai") == "sk-oai-secret1234"
    # raw file actually contains it (documented plaintext-local trade-off)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["keys"]["openai"] == "sk-oai-secret1234"


def test_env_var_fallback(store, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "g-env-key")
    assert store.get_key("google") == "g-env-key"


def test_stored_key_beats_env(store, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "g-env-key")
    store.set_key("google", "g-stored-key")
    assert store.get_key("google") == "g-stored-key"


def test_delete_key(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    store.set_key("anthropic", "sk-ant-abc")
    store.delete_key("anthropic")
    assert store.get_key("anthropic") is None


def test_mask(store):
    store.set_key("anthropic", "sk-ant-abcdefgh1234")
    assert store.mask("anthropic") == "sk-…1234"


def test_mask_missing(store, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert store.mask("openai") is None


def test_defaults_roundtrip(store):
    assert store.get_defaults() == {"provider": "anthropic", "model": "claude-sonnet-4-6"}
    store.set_defaults("openai", "gpt-5.1")
    assert store.get_defaults() == {"provider": "openai", "model": "gpt-5.1"}
