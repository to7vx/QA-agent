"""Run lifecycle endpoints — all owner-scoped.

POST   /runs              enqueue a run (quota + SSRF checked)
GET    /runs              list the current user's runs
GET    /runs/{id}         run summary
GET    /runs/{id}/report  full structured report
GET    /runs/{id}/events  SSE: replay persisted events, then stream live
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from sse_starlette.sse import EventSourceResponse

from ..auth import CurrentUser
from ..byok import MissingProviderKeyError
from ..deps import AppContext, get_ctx, get_current_user, get_current_user_sse
from ..schemas import RunAccepted, RunRequest, RunSummary
from ..security import UnsafeURLError, validate_target_url

router = APIRouter(prefix="/runs", tags=["runs"])

_TERMINAL = {("done", "end"), ("error", "error")}


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


@router.post("", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    body: RunRequest,
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
) -> RunAccepted:
    url = _normalize_url(body.url)

    # SSRF guard (DNS resolution is blocking → threadpool).
    try:
        await run_in_threadpool(validate_target_url, url)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    model = body.model or await run_in_threadpool(ctx.user_settings.default_model, user.id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No model configured. Set one in settings or pass 'model'.",
        )

    # BYOK: reject early if the user has no key for the chosen provider.
    try:
        await run_in_threadpool(
            ctx.user_settings.build_run_settings, user.id, model=model, headless=body.headless
        )
    except MissingProviderKeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Daily cap (DB count) — checked before reserving a concurrency slot.
    today_count = await run_in_threadpool(_runs_today, ctx, user.id)
    if today_count >= ctx.settings.daily_run_cap_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily run limit reached.",
        )

    # Per-user concurrency: atomic check-and-reserve so simultaneous requests
    # can't both slip past the cap.
    if not ctx.jobs.try_reserve(user.id, ctx.settings.max_concurrent_runs_per_user):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many concurrent runs. Wait for a run to finish.",
        )

    run_id = "run_" + uuid.uuid4().hex[:12]
    try:
        await run_in_threadpool(
            ctx.repo.create_run,
            run_id=run_id,
            owner_id=user.id,
            url=url,
            model=model,
            headless=body.headless,
            mode=body.mode,
            auth_profile_id=body.auth_profile_id,
        )
        future = ctx.jobs.submit(
            run_id=run_id,
            owner_id=user.id,
            url=url,
            model=model,
            headless=body.headless,
            heal=body.heal,
            auth_profile_id=body.auth_profile_id,
            mode=body.mode,
            max_pages=body.max_pages,
        )
    except Exception:
        # Reservation must not leak if we never handed work to the pool.
        ctx.jobs.release(user.id)
        raise

    if ctx.settings.run_inline:
        # Deterministic test mode: wait for completion off the event loop.
        await run_in_threadpool(future.result)
    return RunAccepted(run_id=run_id, status="queued")


@router.get("", response_model=list[RunSummary])
async def list_runs(
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[RunSummary]:
    rows = await run_in_threadpool(ctx.repo.list_runs, owner_id=user.id, limit=limit, offset=offset)
    return [RunSummary(**r) for r in rows]


@router.get("/{run_id}", response_model=RunSummary)
async def get_run(
    run_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
) -> RunSummary:
    row = await run_in_threadpool(ctx.repo.get_run_row, run_id=run_id, owner_id=user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return RunSummary(**row)


@router.get("/{run_id}/report")
async def get_report(
    run_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    report = await run_in_threadpool(ctx.repo.get_report, run_id=run_id, owner_id=user.id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return report.model_dump(mode="json")


@router.get("/{run_id}/events")
async def stream_events(
    run_id: str,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    user: CurrentUser = Depends(get_current_user_sse),
) -> EventSourceResponse:
    # Subscribe FIRST so no event published between the ownership check and the
    # live loop can be missed; DB replay + seq dedup reconcile any overlap.
    queue = ctx.bus.subscribe(run_id)

    # Ownership check before opening the stream.
    row = await run_in_threadpool(ctx.repo.get_run_row, run_id=run_id, owner_id=user.id)
    if row is None:
        ctx.bus.unsubscribe(run_id, queue)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    async def generator():
        last_seq = -1
        try:
            # 1. Replay anything already persisted (covers reconnect / mid-run).
            replay = await run_in_threadpool(
                ctx.repo.get_events_since, run_id=run_id, owner_id=user.id, after_seq=last_seq
            )
            for ev in replay:
                last_seq = max(last_seq, ev["seq"])
                yield {"event": "progress", "data": _json(ev)}
                if (ev["phase"], ev["status"]) in _TERMINAL:
                    return

            # If the run already finished before we subscribed, stop.
            if row["status"] in ("succeeded", "failed", "cancelled"):
                yield {"event": "done", "data": _json({"status": row["status"]})}
                return

            # 2. Stream live events, skipping any already replayed.
            while True:
                if await request.is_disconnected():
                    return
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                seq = payload.get("seq", -1)
                if seq != -1 and seq <= last_seq:
                    continue
                last_seq = max(last_seq, seq)
                yield {"event": "progress", "data": _json(payload)}
                if (payload.get("phase"), payload.get("status")) in _TERMINAL:
                    return
        finally:
            ctx.bus.unsubscribe(run_id, queue)

    return EventSourceResponse(generator())


def _runs_today(ctx: AppContext, owner_id: str) -> int:
    from sqlalchemy import func, select

    from ...store.models_orm import RunORM

    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with ctx.db.session() as s:
        return int(
            s.scalar(
                select(func.count())
                .select_from(RunORM)
                .where(RunORM.owner_id == owner_id, RunORM.created_at >= start)
            )
            or 0
        )


def _json(obj: dict) -> str:
    import json

    return json.dumps(obj, default=str)
