"""Tests for the AI test composer."""

from __future__ import annotations

import json

import pytest

from qa_agent.composer import ComposerError, compose
from qa_agent.config import Settings

GOOD_CODE = '''\
from playwright.sync_api import Page, expect


def test_login_error(page: Page):
    page.goto("https://x.test")
    expect(page.get_by_text("Welcome")).to_be_visible()
'''

BROKEN_CODE = "def test_broken(page:\n    pass"


class ScriptedProvider:
    name = "anthropic"
    model = "claude-sonnet-4-6"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def complete(self, system, prompt, max_tokens=4096):
        self.calls += 1
        return self._responses.pop(0)


@pytest.fixture
def settings(tmp_path):
    return Settings(output_dir=tmp_path / "gen", report_dir=tmp_path / "rep")


def test_compose_good_code(settings):
    provider = ScriptedProvider([GOOD_CODE])
    tc = compose(provider, "https://x.test", "log in with wrong password\nexpect error", settings)
    assert tc.name == "log in with wrong password"
    assert tc.playwright_code == GOOD_CODE.rstrip()
    assert tc.tags == ["composed"]
    # file written and registered in manifest
    from pathlib import Path
    assert Path(tc.file_path).exists()
    manifest = json.loads((settings.output_dir / "manifest.json").read_text())
    assert manifest["tests"][0]["test_id"] == tc.id


def test_compose_repairs_broken_code(settings):
    provider = ScriptedProvider([BROKEN_CODE, GOOD_CODE])
    tc = compose(provider, "https://x.test", "scenario", settings)
    assert provider.calls == 2
    assert tc.playwright_code == GOOD_CODE.rstrip()


def test_compose_gives_up_after_one_repair(settings):
    provider = ScriptedProvider([BROKEN_CODE, BROKEN_CODE])
    with pytest.raises(ComposerError):
        compose(provider, "https://x.test", "scenario", settings)


def test_compose_strips_fences(settings):
    provider = ScriptedProvider([f"```python\n{GOOD_CODE}```"])
    tc = compose(provider, "https://x.test", "scenario", settings)
    assert "```" not in tc.playwright_code


def test_manifest_appends(settings):
    compose(ScriptedProvider([GOOD_CODE]), "https://x.test", "first", settings)
    compose(ScriptedProvider([GOOD_CODE]), "https://x.test", "second", settings)
    manifest = json.loads((settings.output_dir / "manifest.json").read_text())
    assert len(manifest["tests"]) == 2
