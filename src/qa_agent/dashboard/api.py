"""REST + SSE API for the dashboard."""

from __future__ import annotations

import asyncio
import concurrent.futures
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..composer import ComposerError, compose_with_snapshot
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


class ComposeBody(BaseModel):
    url: str
    scenario: str
    provider: str = "anthropic"
    model: str = ""


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

        def _probe() -> None:
            provider = create_provider(
                provider_id, PROVIDERS[provider_id].default_model, key
            )
            # A raised exception means a bad key/network; an empty-but-clean
            # response (some reasoning models) still proves the key works.
            provider.complete("Reply with exactly: OK", "ping", max_tokens=64)

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(_probe)
        pool.shutdown(wait=False)  # don't block the response on a hung probe
        try:
            future.result(timeout=20)
            return {"ok": True}
        except concurrent.futures.TimeoutError:
            return {"ok": False, "error": "Provider did not respond within 20 seconds."}
        except ProviderError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"Unexpected error: {exc}"}

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

    @app.post("/api/runs/{run_id}/rerun-failed", status_code=201)
    def rerun_failed(run_id: str):
        try:
            new_id = manager.rerun_failed(run_id)
        except RunBusyError as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        except ProviderError as exc:
            raise HTTPException(400, str(exc))
        return {"run_id": new_id}

    @app.get("/api/runs/{run_id}/code/{test_case_id}")
    def get_test_code(run_id: str, test_case_id: str):
        payload = manager.get_report(run_id)
        if payload is None or not payload.get("report"):
            raise HTTPException(404, "Run not found.")
        for tc in payload["report"].get("test_cases", []):
            if tc.get("id") == test_case_id:
                code = tc.get("playwright_code") or _read_generated_file(
                    settings, tc.get("file_path", "")
                )
                if not code:
                    raise HTTPException(404, "Test source is no longer available.")
                return {"code": code, "file_path": tc.get("file_path", "")}
        raise HTTPException(404, "Test not found in this run.")

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    @app.get("/api/insights")
    def insights():
        return manager.store.insights()

    # ------------------------------------------------------------------
    # Test library + composer
    # ------------------------------------------------------------------

    @app.get("/api/tests")
    def list_tests():
        return {"tests": manager.store.list_test_cases()}

    @app.get("/api/tests/{tc_id}")
    def get_test(tc_id: str):
        tc = manager.store.get_test_case(tc_id)
        if tc is None:
            raise HTTPException(404, "Test case not found.")
        return tc

    @app.delete("/api/tests/{tc_id}")
    def delete_test(tc_id: str):
        tc = manager.store.get_test_case(tc_id)
        if tc is None:
            raise HTTPException(404, "Test case not found.")
        manager.store.delete_test_case(tc_id)
        safe_path = _resolve_under_output(settings, tc["file_path"])
        if safe_path is not None and safe_path.exists():
            try:
                safe_path.unlink()
            except OSError:
                pass
        return {"deleted": True}

    @app.post("/api/tests/{tc_id}/run", status_code=201)
    def run_test(tc_id: str):
        try:
            run_id = manager.run_single_test(tc_id)
        except RunBusyError as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        except ProviderError as exc:
            raise HTTPException(400, str(exc))
        return {"run_id": run_id}

    @app.post("/api/compose", status_code=201)
    async def compose_test(body: ComposeBody):
        _validate_provider(body.provider)
        if not body.url.startswith(("http://", "https://")):
            raise HTTPException(400, "URL must start with http:// or https://")
        if len(body.scenario.strip()) < 10:
            raise HTTPException(400, "Describe the scenario in a bit more detail.")
        key = keystore.get_key(body.provider)
        if not key:
            raise HTTPException(
                400,
                f"No API key configured for provider '{body.provider}'. "
                "Add one on the Settings page first.",
            )
        provider = create_provider(body.provider, body.model, key)
        compose_settings = settings.model_copy()
        compose_settings.provider = body.provider
        compose_settings.model = provider.model
        try:
            tc = await asyncio.to_thread(
                lambda: asyncio.run(
                    compose_with_snapshot(provider, body.url, body.scenario, compose_settings)
                )
            )
        except ComposerError as exc:
            raise HTTPException(422, str(exc))
        except ProviderError as exc:
            raise HTTPException(400, str(exc))
        record = {
            "id": tc.id,
            "name": tc.name,
            "description": tc.description,
            "scenario": body.scenario.strip(),
            "url": body.url,
            "file_path": tc.file_path,
            "code": tc.playwright_code,
            "origin": "composed",
            "provider": provider.name,
            "model": provider.model,
            "tags": tc.tags,
        }
        try:
            manager.store.add_test_case(record)
        except Exception:
            pass  # library write is best-effort; the file itself exists
        return record

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


def _resolve_under_output(settings: Settings, file_path: str) -> Path | None:
    """Resolve a stored path and confirm it lives under output_dir (no traversal)."""
    if not file_path:
        return None
    try:
        resolved = Path(file_path).resolve()
        output_root = settings.output_dir.resolve()
        if resolved.is_relative_to(output_root):
            return resolved
    except (OSError, ValueError):
        pass
    return None


def _read_generated_file(settings: Settings, file_path: str) -> str | None:
    safe = _resolve_under_output(settings, file_path)
    if safe is None or not safe.exists():
        return None
    try:
        return safe.read_text(encoding="utf-8")
    except OSError:
        return None
