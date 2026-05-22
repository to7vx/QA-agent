"""Structured progress events emitted by the pipeline.

The CLI renders progress with Rich; the API needs the same milestones as
machine-readable events to stream over SSE and persist for replay. The pipeline
emits :class:`ProgressEvent`s through an :class:`EventEmitter`; when no sink is
attached (the CLI case) emission is a no-op, so behavior is unchanged.

This lives in the core package (not ``api``) so ``agent``/``generator``/
``executor`` never import the web layer.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Phase = Literal["explore", "generate", "write", "execute", "heal", "report", "done", "error"]
Status = Literal["start", "progress", "item_done", "end", "error"]


class ProgressEvent(BaseModel):
    run_id: str = ""
    seq: int = 0
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    phase: Phase
    status: Status
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


ProgressHook = Callable[[ProgressEvent], None]


class EventEmitter:
    """Stamps run_id + a monotonic seq onto events and forwards to a sink.

    A ``None`` sink makes :meth:`emit` a no-op — the CLI path. The sink must
    never raise; if it does, the error is swallowed so telemetry can't break a
    run.
    """

    def __init__(self, run_id: str = "", sink: ProgressHook | None = None) -> None:
        self.run_id = run_id
        self._sink = sink
        self._seq = 0

    @property
    def enabled(self) -> bool:
        return self._sink is not None

    def emit(
        self,
        phase: Phase,
        status: Status,
        message: str = "",
        **data: Any,
    ) -> None:
        if self._sink is None:
            return
        event = ProgressEvent(
            run_id=self.run_id,
            seq=self._seq,
            phase=phase,
            status=status,
            message=message,
            data=data,
        )
        self._seq += 1
        # pragma: no cover - telemetry must never break a run
        with suppress(Exception):
            self._sink(event)


# A shared no-op emitter for callers that don't supply one (keeps call sites
# free of None-checks).
NULL_EMITTER = EventEmitter()
