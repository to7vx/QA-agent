"""REST + SSE API for the dashboard."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..keystore import KeyStore
from ..providers import PROVIDERS, ProviderError, create_provider
from .run_manager import RunBusyError, RunManager, RunParams

STATIC_DIR = Path(__file__).parent / "static"


class KeyBody(BaseModel):
    api_key: str


class DefaultsBody(BaseModel):
    provider: str
    model: str


def create_app(
    manager: RunManager | None = None,
    keystore: KeyStore | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    keystore = keystore or KeyStore()
    manager = manager or RunManager(settings=settings, keystore=keystore)

    app = FastAPI(title="qa-agent dashboard", docs_url=None, redoc_url=None)

    # ------------------------------------------------------------------
    # Providers & settings
    # ------------------------------------------------------------------

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/providers")
    def providers():
        return [
            {
                "id": info.id,
                "label": info.label,
                "models": info.models,
                "default_model": info.default_model,
                "configured": keystore.get_key(info.id) is not None,
                "masked_key": keystore.mask(info.id),
            }
            for info in PROVIDERS.values()
        ]

    @app.get("/api/settings")
    def get_settings_route():
        return {
            "defaults": keystore.get_defaults(),
            "providers": {
                pid: {
                    "configured": keystore.get_key(pid) is not None,
                    "masked_key": keystore.mask(pid),
                }
                for pid in PROVIDERS
            },
        }

    @app.put("/api/settings/keys/{provider_id}")
    def set_key(provider_id: str, body: KeyBody):
        _validate_provider(provider_id)
        key = body.api_key.strip()
        if not key:
            raise HTTPException(400, "API key must not be empty.")
        keystore.set_key(provider_id, key)
        return {"configured": True, "masked_key": keystore.mask(provider_id)}

    @app.delete("/api/settings/keys/{provider_id}")
    def delete_key(provider_id: str):
        _validate_provider(provider_id)
        keystore.delete_key(provider_id)
        return {"configured": keystore.get_key(provider_id) is not None}

    @app.post("/api/settings/keys/{provider_id}/test")
    def test_key(provider_id: str):
        _validate_provider(provider_id)
        key = keystore.get_key(provider_id)
        if not key:
            raise HTTPException(400, "No key configured for this provider.")
        try:
            provider = create_provider(
                provider_id, PROVIDERS[provider_id].default_model, key
            )
            provider.complete("Reply with exactly: OK", "ping", max_tokens=16)
            return {"ok": True}
        except ProviderError as exc:
            return {"ok": False, "error": str(exc)}

    @app.put("/api/settings/defaults")
    def set_defaults(body: DefaultsBody):
        _validate_provider(body.provider)
        keystore.set_defaults(body.provider, body.model)
        return keystore.get_defaults()

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    @app.post("/api/runs", status_code=201)
    def start_run(params: RunParams):
        _validate_provider(params.provider)
        if not params.url.startswith(("http://", "https://")):
            raise HTTPException(400, "URL must start with http:// or https://")
        try:
            run_id = manager.start(params)
        except RunBusyError as exc:
            raise HTTPException(409, str(exc))
        except ProviderError as exc:
            raise HTTPException(400, str(exc))
        return {"run_id": run_id}

    @app.get("/api/runs")
    def list_runs():
        return {"runs": manager.history(), "active": manager.active_run()}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        payload = manager.get_report(run_id)
        if payload is None:
            raise HTTPException(404, "Run not found.")
        return payload

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str):
        if not manager.cancel(run_id):
            raise HTTPException(409, "Run is not active.")
        return {"cancelling": True}

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str):
        if manager.status(run_id) is None:
            raise HTTPException(404, "Run not found.")

        async def stream():
            index = 0
            while True:
                events, done = manager.events_since(run_id, index)
                for event in events:
                    yield f"data: {event.model_dump_json()}\n\n"
                index += len(events)
                if done and not events:
                    yield 'event: done\ndata: {}\n\n'
                    return
                if not events:
                    await asyncio.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ------------------------------------------------------------------
    # Static: screenshots + SPA
    # ------------------------------------------------------------------

    screenshots_dir = settings.report_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/screenshots", StaticFiles(directory=screenshots_dir), name="screenshots")

    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            candidate = STATIC_DIR / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return app


def _validate_provider(provider_id: str) -> None:
    if provider_id not in PROVIDERS:
        raise HTTPException(
            400, f"Unknown provider '{provider_id}'. Choose one of: {', '.join(PROVIDERS)}"
        )
