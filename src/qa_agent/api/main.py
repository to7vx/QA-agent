"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..store.engine import make_database
from ..store.repository import RunRepository
from .byok import UserSettingsService
from .crypto import SecretBox
from .deps import AppContext
from .events import EventBus
from .jobs import RunJobManager
from .profiles import AuthProfileService
from .routers import analytics, auth_profiles, runs
from .routers import settings as settings_router
from .settings import ApiSettings, get_api_settings

log = logging.getLogger("qa_agent.api")


def create_app(api_settings: ApiSettings | None = None) -> FastAPI:
    api_settings = api_settings or get_api_settings()

    db = make_database(api_settings.database_url)
    # SQLite (tests/dev) has no Alembic step — create tables on boot. Postgres
    # is migrated with Alembic, so we never auto-create there.
    if api_settings.database_url.startswith("sqlite"):
        db.create_all()

    repo = RunRepository(db)
    bus = EventBus()
    box = SecretBox(api_settings.secret_key)
    user_settings = UserSettingsService(db, box)
    profiles = AuthProfileService(db, box)
    jobs = RunJobManager(
        repo=repo,
        bus=bus,
        user_settings=user_settings,
        profiles=profiles,
        max_workers=max(2, api_settings.max_concurrent_runs_per_user * 4),
        parallelism=api_settings.parallelism,
    )

    ctx = AppContext(
        settings=api_settings,
        db=db,
        repo=repo,
        bus=bus,
        box=box,
        user_settings=user_settings,
        profiles=profiles,
        jobs=jobs,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.bind_loop(asyncio.get_running_loop())
        if box.is_ephemeral:
            log.warning("Running with an ephemeral encryption key.")
        yield
        jobs.shutdown()
        db.dispose()

    app = FastAPI(title="QA Agent API", version="1.0.0", lifespan=lifespan)
    app.state.ctx = ctx

    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "auth_disabled": api_settings.auth_disabled}

    app.include_router(runs.router)
    app.include_router(analytics.router)
    app.include_router(settings_router.router)
    app.include_router(auth_profiles.router)
    return app
