"""Crawler pure helpers (no browser) + parallel executor (trivial real tests)."""

from __future__ import annotations

from pathlib import Path

from qa_agent.config import Settings
from qa_agent.crawler import _unique_flow_id, extract_links, normalize_url, same_origin
from qa_agent.executor import Executor
from qa_agent.models import TestCase, TestStatus

# --- URL helpers -----------------------------------------------------------


def test_normalize_url_strips_fragment_and_trailing_slash() -> None:
    assert normalize_url("https://a.com/x/#section") == "https://a.com/x"
    assert normalize_url("https://a.com/") == "https://a.com/"  # root keeps slash
    assert normalize_url("/about", "https://a.com/home") == "https://a.com/about"


def test_same_origin() -> None:
    assert same_origin("https://a.com/x", "https://a.com/y") is True
    assert same_origin("https://a.com", "http://a.com") is False  # scheme differs
    assert same_origin("https://a.com", "https://b.com") is False


def test_extract_links_dedupes_and_scopes() -> None:
    elements = [
        {"type": "link", "href": "https://a.com/one"},
        {"type": "link", "href": "https://a.com/one#frag"},  # dup after normalize
        {"type": "link", "href": "/two"},  # relative → resolved
        {"type": "link", "href": "https://other.com/x"},  # off-origin
        {"type": "link", "href": "mailto:hi@a.com"},  # skipped
        {"type": "button", "selector": "#btn"},  # not a link
    ]
    links = extract_links(elements, "https://a.com/home", restrict_same_origin=True)
    assert links == ["https://a.com/one", "https://a.com/two"]


def test_extract_links_allows_offsite_when_unrestricted() -> None:
    elements = [{"type": "link", "href": "https://other.com/x"}]
    links = extract_links(elements, "https://a.com", restrict_same_origin=False)
    assert "https://other.com/x" in links


def test_unique_flow_id_suffixes_collisions() -> None:
    seen: set[str] = set()
    # The LLM reuses ids like 'flow_reg01' across crawled pages.
    assert _unique_flow_id("flow_reg01", seen) == "flow_reg01"
    assert _unique_flow_id("flow_reg01", seen) == "flow_reg01_2"
    assert _unique_flow_id("flow_reg01", seen) == "flow_reg01_3"
    assert _unique_flow_id("flow_other", seen) == "flow_other"
    assert seen == {"flow_reg01", "flow_reg01_2", "flow_reg01_3", "flow_other"}


# --- parallel executor -----------------------------------------------------


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="x",
        model="anthropic/claude-sonnet-4-6",
        output_dir=tmp_path / "gen",
        report_dir=tmp_path / "rep",
    )


def _write_trivial_test(dir_: Path, name: str, passing: bool) -> TestCase:
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / f"test_{name}.py"
    body = "def test_x():\n    assert True\n" if passing else "def test_x():\n    assert False\n"
    path.write_text(body, encoding="utf-8")
    return TestCase(id=name, flow_id=name, name=name, description="", file_path=str(path))


def test_run_parallel_executes_all(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.ensure_dirs()
    gen = settings.output_dir
    cases = [
        _write_trivial_test(gen, "a", True),
        _write_trivial_test(gen, "b", False),
        _write_trivial_test(gen, "c", True),
    ]
    ex = Executor(settings)
    results, attempts = ex.run_parallel(cases, healer=None, max_workers=3)

    by_id = {r.test_case_id: r for r in results}
    assert len(results) == 3
    assert by_id["a"].status == TestStatus.PASSED
    assert by_id["c"].status == TestStatus.PASSED
    assert by_id["b"].status == TestStatus.FAILED
    assert attempts == []

    # Per-test screenshot dirs were created (isolation).
    assert (settings.report_dir / "screenshots").exists()


def test_run_parallel_falls_back_for_single(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.ensure_dirs()
    case = _write_trivial_test(settings.output_dir, "only", True)
    ex = Executor(settings)
    results, _ = ex.run_parallel([case], max_workers=4)
    assert len(results) == 1
    assert results[0].status == TestStatus.PASSED
