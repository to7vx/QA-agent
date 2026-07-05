"""Tests for the RunEvent model."""

from __future__ import annotations

from qa_agent.events import EVENT_TYPES, RunEvent


def test_event_defaults():
    ev = RunEvent(type="stage", data={"stage": "explore"})
    assert ev.type == "stage"
    assert ev.data["stage"] == "explore"
    assert ev.timestamp.tzinfo is not None


def test_event_serializes_to_json():
    ev = RunEvent(type="run_started", data={"url": "https://example.com"})
    payload = ev.model_dump_json()
    assert "run_started" in payload
    assert "example.com" in payload


def test_known_event_types_documented():
    assert "test_result" in EVENT_TYPES
    assert "run_error" in EVENT_TYPES
