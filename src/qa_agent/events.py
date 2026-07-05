"""Run progress events streamed from the agent to the dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field

# run_started | stage | flows_found | test_generated | test_started
# | test_result | healing | log | run_finished | run_error | cancelled
EVENT_TYPES = {
    "run_started",
    "stage",
    "flows_found",
    "test_generated",
    "test_started",
    "test_result",
    "healing",
    "log",
    "run_finished",
    "run_error",
    "cancelled",
}


class RunEvent(BaseModel):
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


EmitFn = Callable[[RunEvent], None]
