"""Analytics endpoints — owner-scoped aggregates for the dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from ..auth import CurrentUser
from ..deps import AppContext, get_ctx, get_current_user
from ..schemas import AnalyticsSummary, TrendPoint

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def summary(
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
) -> AnalyticsSummary:
    data = await run_in_threadpool(ctx.repo.summary, owner_id=user.id)
    return AnalyticsSummary(**data)


@router.get("/pass-rate-trend", response_model=list[TrendPoint])
async def pass_rate_trend(
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(30, ge=1, le=200),
) -> list[TrendPoint]:
    points = await run_in_threadpool(ctx.repo.pass_rate_trend, owner_id=user.id, limit=limit)
    return [TrendPoint(**p) for p in points]


@router.get("/healing")
async def healing_stats(
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, int]:
    return await run_in_threadpool(ctx.repo.healing_stats, owner_id=user.id)
