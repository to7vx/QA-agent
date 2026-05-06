"""Centralized Claude prompt templates."""

EXPLORE_SYSTEM = """\
You are an expert QA engineer analyzing a web application.
Your task is to identify key user flows and interactions on the page.
Be thorough and systematic. Focus on flows a real user would exercise.
Return structured JSON only — no prose outside the JSON block.\
"""

EXPLORE_USER = """\
Analyze the following page snapshot from {url} and identify the main user flows.

PAGE SNAPSHOT:
{snapshot}

Return a JSON array of flow objects with this exact schema:
[
  {{
    "id": "flow_<short_id>",
    "name": "Human-readable flow name",
    "description": "What this flow accomplishes",
    "url": "{url}",
    "steps": [
      {{
        "description": "Step description",
        "selector": "CSS selector or null",
        "action": "click | fill | navigate | assert | null",
        "expected_result": "What should happen or null"
      }}
    ],
    "tags": ["authentication", "navigation", ...]
  }}
]
Identify at least 3 flows. Prefer flows that cover happy paths, error cases, and edge cases.\
"""

GENERATE_SYSTEM = """\
You are an expert QA engineer writing Playwright tests in Python.
Write clean, maintainable async Playwright tests using pytest-playwright.
Each test should be self-contained and follow AAA (Arrange, Act, Assert) structure.
Use explicit waits, never time.sleep(). Handle failures gracefully.
Return valid Python code only — no markdown fences, no prose.\
"""

GENERATE_USER = """\
Generate a complete pytest-playwright test file for the following user flow:

FLOW:
{flow_json}

Requirements:
- Use `async def test_*` functions with `async_generator` fixture
- Import: `import pytest`, `from playwright.async_api import Page, expect`
- Base URL: {url}
- Include a docstring describing what the test covers
- Add explicit `await page.wait_for_load_state("networkidle")` after navigations
- Assert meaningful outcomes, not just "no error occurred"
- File should be importable with no side effects\
"""

ANALYZE_FAILURE_SYSTEM = """\
You are a QA engineer analyzing a failed Playwright test.
Given the error output and test code, provide a concise root-cause analysis
and suggest a fix. Be direct and actionable.\
"""

ANALYZE_FAILURE_USER = """\
The following Playwright test failed:

TEST CODE:
{test_code}

ERROR OUTPUT:
{error_output}

Provide:
1. Root cause (1-2 sentences)
2. Suggested fix (code snippet if applicable)
3. Confidence level: high / medium / low\
"""
