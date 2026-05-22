"""Dependency wiring: app context container + auth dependency."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Query, Request, status

from ..store.engine import Database
from ..store.repository import RunRepository
from .auth import AuthError, CurrentUser, verify_token
from .byok import UserSettingsService
from .crypto import SecretBox
from .events import EventBus
from .jobs import RunJobManager
from .profiles import AuthProfileService
from .settings import ApiSettings


@dataclass
class AppContext:
    settings: ApiSettings
    db: Database
    repo: RunRepository
    bus: EventBus
    box: SecretBox
    user_settings: UserSettingsService
    profiles: AuthProfileService
    jobs: RunJobManager


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def _resolve_user(ctx: AppContext, token: str | None) -> CurrentUser:
    settings = ctx.settings
    if settings.auth_disabled:
        return CurrentUser(id=settings.dev_user_id, email="dev@example.com")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return verify_token(token, settings)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def get_current_user(
    ctx: AppContext = Depends(get_ctx),
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    """Resolve the user from the Authorization Bearer header (all routes)."""
    return _resolve_user(ctx, _bearer(authorization))


def get_current_user_sse(
    ctx: AppContext = Depends(get_ctx),
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
) -> CurrentUser:
    """SSE-only variant that also accepts an ``access_token`` query param.

    ``EventSource`` cannot set headers, so the dashboard passes the Supabase
    token in the URL. This is scoped to the SSE route so the token-in-URL
    surface (server/proxy logs) is not opened on every endpoint.
    """
    token = _bearer(authorization) or (access_token.strip() if access_token else None)
    return _resolve_user(ctx, token)
