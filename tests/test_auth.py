"""Supabase JWT verification + crypto round-trip."""

from __future__ import annotations

import time

import jwt
import pytest

from qa_agent.api.auth import AuthError, verify_token
from qa_agent.api.crypto import SecretBox, generate_key
from qa_agent.api.settings import ApiSettings

SECRET = "super-secret-jwt-signing-key-with-enough-length-1234567890"


def _settings() -> ApiSettings:
    return ApiSettings(supabase_jwt_secret=SECRET, jwt_audience="authenticated")


def _token(**overrides) -> str:
    payload = {
        "sub": "user-123",
        "email": "a@b.com",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    payload.update(overrides)
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_verify_valid_token() -> None:
    user = verify_token(_token(), _settings())
    assert user.id == "user-123"
    assert user.email == "a@b.com"


def test_reject_bad_signature() -> None:
    bad = jwt.encode(
        {"sub": "x", "aud": "authenticated", "exp": int(time.time()) + 60},
        "wrong-secret-also-long-enough-1234567890-abcdef",
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        verify_token(bad, _settings())


def test_reject_expired_token() -> None:
    with pytest.raises(AuthError):
        verify_token(_token(exp=int(time.time()) - 10), _settings())


def test_reject_wrong_audience() -> None:
    with pytest.raises(AuthError):
        verify_token(_token(aud="other"), _settings())


def test_missing_secret_raises() -> None:
    with pytest.raises(AuthError):
        verify_token(_token(), ApiSettings(supabase_jwt_secret=None))


def test_secret_box_roundtrip() -> None:
    box = SecretBox(generate_key())
    token = box.encrypt("sk-ant-secret")
    assert token != b"sk-ant-secret"
    assert box.decrypt(token) == "sk-ant-secret"
    assert box.decrypt(None) is None
