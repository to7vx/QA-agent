"""Structured logging, request-ID correlation, and optional Sentry.

Kept dependency-light: JSON logs via a tiny custom formatter, a request-ID
carried on a contextvar so every log line in a request is correlated, and a
guarded Sentry init that is a no-op unless ``SENTRY_DSN`` is set.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Set per request; included on every log record via RequestIdFilter.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", *, json_logs: bool = True) -> None:
    """Install a single stream handler with request-ID correlation."""
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # LiteLLM stays noisy; keep it quiet (matches the core llm module).
    logging.getLogger("LiteLLM").setLevel(logging.ERROR)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a request ID and echo it back in the response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response


def init_sentry(dsn: str | None) -> bool:
    """Initialize Sentry if a DSN is provided and the SDK is installed."""
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logging.getLogger("qa_agent.api").warning(
            "SENTRY_DSN set but sentry-sdk not installed (pip install '.[observability]')."
        )
        return False
    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)
    return True
