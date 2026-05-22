"""Supabase JWT verification.

Supabase mints HS256 JWTs signed with the project's JWT secret. We verify the
signature + audience and extract the user id (``sub``). When auth is disabled
(dev/tests) every request resolves to a single configured user id.
"""

from __future__ import annotations

import jwt
from pydantic import BaseModel

from .settings import ApiSettings


class CurrentUser(BaseModel):
    id: str
    email: str | None = None
    role: str | None = None


class AuthError(Exception):
    """Raised when a token is missing or invalid."""


def verify_token(token: str, settings: ApiSettings) -> CurrentUser:
    if not settings.supabase_jwt_secret:
        raise AuthError("Server is missing SUPABASE_JWT_SECRET; cannot verify tokens.")
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise AuthError("Token has no subject.")
    return CurrentUser(id=str(sub), email=payload.get("email"), role=payload.get("role"))
