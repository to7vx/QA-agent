"""Per-user settings endpoints (BYOK provider keys + default model).

Keys are write-only: the API accepts plaintext over HTTPS, stores it encrypted,
and never returns it. GET exposes only booleans (key present / not).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from ..auth import CurrentUser
from ..deps import AppContext, get_ctx, get_current_user
from ..schemas import UserSettingsResponse, UserSettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsResponse)
async def get_settings(
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
) -> UserSettingsResponse:
    data = await run_in_threadpool(ctx.user_settings.get_masked, user.id)
    return UserSettingsResponse(**data)


@router.put("", response_model=UserSettingsResponse)
async def update_settings(
    body: UserSettingsUpdate,
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
) -> UserSettingsResponse:
    data = await run_in_threadpool(
        ctx.user_settings.update,
        user.id,
        anthropic_key=body.anthropic_key,
        gemini_key=body.gemini_key,
        default_model=body.default_model,
        clear_anthropic=body.clear_anthropic,
        clear_gemini=body.clear_gemini,
    )
    return UserSettingsResponse(**data)
