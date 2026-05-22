"""Auth-profile endpoints — manage stored login sessions (owner-scoped).

The encrypted storage_state is never returned; only metadata is listed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..auth import CurrentUser
from ..deps import AppContext, get_ctx, get_current_user

router = APIRouter(prefix="/auth-profiles", tags=["auth-profiles"])


class AuthProfileCreate(BaseModel):
    name: str
    origin: str = ""
    # Playwright storage_state captured client-side or via `qa-agent auth capture`.
    storage_state: dict[str, Any]


@router.get("")
async def list_profiles(
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    if ctx.profiles is None:
        return []
    return await run_in_threadpool(ctx.profiles.list, user.id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: AuthProfileCreate,
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    if ctx.profiles is None:
        raise HTTPException(status_code=503, detail="Auth profiles unavailable.")
    return await run_in_threadpool(
        ctx.profiles.create,
        user.id,
        name=body.name,
        origin=body.origin,
        storage_state=body.storage_state,
    )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
) -> None:
    if ctx.profiles is None or not await run_in_threadpool(
        ctx.profiles.delete, user.id, profile_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
