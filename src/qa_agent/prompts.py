"""Centralized Claude prompt templates.

All strings passed to the Anthropic client must be defined here as module-level
constants — never inline in the calling code.
"""

# ---------------------------------------------------------------------------
# Explorer: page analysis → list[Flow]
# ---------------------------------------------------------------------------

EXPLORER_SYSTEM = """\
You are an expert QA engineer analyzing a live web page.
Your job is to identify the distinct user flows a test suite should cover.
Think like someone writing a comprehensive regression suite:
cover the happy path, error conditions, and meaningful edge cases.
Be specific — each step must be concrete enough to drive a Playwright test.
Return structured JSON only. No markdown, no explanation, no prose.\
"""

EXPLORER_PROMPT = """\
Analyze this web page and identify 3-7 user flows a QA engineer should test.

{context}

## Output schema

Return a JSON array. Every element must match this exact shape:
{{
  "id": "flow_<4-6 char alphanumeric id>",
  "name": "Short descriptive name (3-6 words)",
  "description": "What this flow validates and why it matters (1-2 sentences)",
  "url": "<the URL where this flow starts>",
  "priority": "high | medium | low",
  "steps": [
    {{
      "description": "Action in plain English — always start with a verb (Click, Fill, Navigate, Assert, Submit, Select, Hover)",
      "selector": "CSS selector for the target element, or null if not element-specific",
      "action": "click | fill | navigate | assert | hover | select | submit | null",
      "expected_result": "Observable outcome a test can verify (text appears, URL changes, element visible), or null"
    }}
  ],
  "tags": ["one", "or", "more", "category", "tags"]
}}

## Priority rules
- high: core functionality — the site is broken without it (login, search, primary form, checkout)
- medium: important secondary flows (filtering, navigation, profile editing, settings)
- low: edge cases, error recovery, secondary interactions

## Quality constraints
- Every flow must be independently executable starting from its "url"
- Selectors must prefer stable attributes: id > name > aria-label > role > text > class
- Expected results must be observable and verifiable by a test (not "user feels happy")
- Do not describe flows for features that are not visible on this page
- Steps must be granular enough that each one maps to a single Playwright action

Return the JSON array only. No other text.\
"""

# ---------------------------------------------------------------------------
# Generator: Flow → Playwright test file
# ---------------------------------------------------------------------------

GENERATOR_SYSTEM = """\
You are an expert Python QA engineer writing Playwright tests.
Tests use pytest-playwright with the SYNCHRONOUS API: the `page` fixture is a
sync Playwright Page already connected to a Chromium browser. Test functions
are plain `def test_*` — NEVER `async def`. NEVER use `await`. NEVER import
from `playwright.async_api`.
You write tests that are readable, maintainable, and resilient to minor UI changes.
Return only valid Python source code — no markdown fences, no explanation, no prose.\
"""

GENERATOR_PROMPT = """\
Generate a runnable pytest-playwright test file for the user flow below.

## Flow to implement
{flow_json}

## Page context (use this to choose the best selectors)
{page_context}

## Selector preference — use the first that applies
1. `page.get_by_role("button", name="Submit")`      — role + accessible name (most resilient)
2. `page.get_by_label("Email address")`              — matches <label> text
3. `page.get_by_placeholder("Search...")`            — input placeholder
4. `page.get_by_text("Exact visible text")`          — visible text content
5. `page.locator("#stable-id")`                      — ID attribute
6. `page.locator("[name='field-name']")`             — name attribute
7. `page.locator(".css-class")`                      — class (last resort, fragile)

Combine selectors with `.filter()` or `.nth()` when the page has duplicate roles.

## Required test structure (SYNC API — no async, no await)
```python
\"\"\"<One sentence: what this test file covers.>\"\"\"
from playwright.sync_api import Page, expect


def test_<snake_case_flow_name>(page: Page) -> None:
    \"\"\"<One sentence describing what success looks like.>\"\"\"
    # --- Arrange: navigate to starting URL ---
    page.goto("<url>", wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=5_000)
    except Exception:
        pass  # page may have long-polling; proceed anyway

    # --- Act: <step group description> ---
    # <comment explaining why this action matters>
    page.get_by_role(...).click()

    # --- Assert: <what we verify> ---
    expect(page.get_by_role(...)).to_be_visible()
```

## Code rules
- One function per file, named `test_<flow_name_in_snake_case>`
- Test function is `def`, NOT `async def`. No `await` anywhere in the file.
- Import only from `playwright.sync_api` — never `playwright.async_api`.
- Module docstring at the top (one sentence)
- Function docstring (one sentence describing success)
- One comment per logical step block explaining intent, not mechanics
- Use `expect(locator).to_be_visible()` — not bare `assert`
- Use `expect(page).to_have_url(pattern)` for URL assertions
- Stateful inputs (checkbox, radio, toggle, select):
  - Never assume the initial state. The page snapshot includes `checked` /
    `selected_value` / `current_value` — read those before asserting.
  - Prefer the idempotent helpers `locator.check()` and `locator.uncheck()`
    over `.click()` — they no-op if the input is already in the target state,
    so the test stays correct regardless of initial state.
  - For `<select>`, use `locator.select_option(value=...)`, then assert with
    `expect(locator).to_have_value(...)`.
  - After `check()` assert `to_be_checked()`; after `uncheck()` assert
    `not_to_be_checked()`. Never click and then assert the opposite of what
    you guessed the previous state was.
- Text assertions:
  - Prefer `expect(locator).to_contain_text("stable substring")` when the surrounding
    text may vary (A/B tests, timestamps, counts, dynamic IDs).
  - `to_have_text` does an EXACT string match — never put regex syntax like
    `|`, `(...)`, `.*`, `?` inside a plain string. If you need a pattern, import
    `re` and pass `re.compile(r"A/B Test (Control|Variation 1)")` instead.
  - Same rule for `to_have_url`: use `re.compile(...)` for patterns, not raw
    strings with regex metacharacters.
- Wrap every `wait_for_load_state("networkidle")` in try/except — pages with polling never settle
- No `time.sleep()`, no `asyncio.sleep()`, no hardcoded numeric waits
- The final lines must contain at least one `expect(...)` assertion
- If a step has a selector from the flow data, use it as a fallback hint only —
  prefer the role/label/text selectors above if they are unambiguous

Return valid Python source only. Nothing before the module docstring, nothing after the last line of code.\
"""

# ---------------------------------------------------------------------------
# Repair: fix a syntax-broken generated test
# ---------------------------------------------------------------------------

REPAIR_SYSTEM = """\
You are a Python syntax fixer. You receive broken Python code and a SyntaxError message.
Return the corrected code only — no explanation, no markdown fences, no prose.\
"""

REPAIR_PROMPT = """\
This Python file has a syntax error. Fix it and return the corrected source.

## Error
{error}

## Broken code
{code}

Return corrected Python source only.\
"""

# ---------------------------------------------------------------------------
# Failure analysis: error output → root cause + fix suggestion
# ---------------------------------------------------------------------------

ANALYZE_FAILURE_SYSTEM = """\
You are a senior QA engineer diagnosing a failed Playwright test.
Be direct and specific. Avoid generic advice like "check your selectors".
Name the actual problem and give a concrete, copy-pasteable fix.\
"""

ANALYZE_FAILURE_PROMPT = """\
This Playwright test failed. Diagnose it.

## Test code
```python
{test_code}
```

## Error output
```
{error_output}
```

Respond in this exact format — no other text:

**Root cause:** <1-2 sentences identifying the specific problem>

**Fix:**
```python
<corrected code snippet, or the specific line(s) to change>
```

**Confidence:** high | medium | low\
"""

# ---------------------------------------------------------------------------
# Healer: failing selector → replacement selector
# ---------------------------------------------------------------------------

HEALER_SYSTEM = """\
You are a Playwright test selector repair specialist.
Your sole job is to find the current DOM element that a test was previously targeting
under a different selector.

Strict matching rules:
- Match on semantic identity: role, accessible name, visible label, and purpose.
  A "Submit" button must map to another submit-like button — not any button on the page.
- If the original element type no longer exists (e.g., a login form has been removed),
  set refused=true.
- Never return a selector that points to a different logical element than the original.
- Confidence scale: 1.0 = unambiguous match, 0.7 = clear match with minor uncertainty,
  below 0.7 = refuse rather than guess.
- Prefer Playwright role/label/text selectors over CSS or XPath.
Return JSON only. No markdown, no explanation outside the JSON.\
"""

HEALER_PROMPT = """\
A Playwright test failed because its selector no longer matches any element on the page.
Identify the replacement selector for the same logical element.

## Failing test code
```python
{test_code}
```

## Failing selector (as it appears after "page.")
{failing_selector}

## Error message
{error_message}

## Current page DOM (truncated)
```html
{dom}
```

## Accessibility tree
```json
{ax_tree}
```

## Task
1. Determine what logical element the failing selector targeted: its type, role, label, visible text, and purpose.
2. Search the DOM and accessibility tree for that exact logical element.
3. If found with confidence >= 0.7, return the Playwright expression that best targets it.
4. If the element does not exist on this page, or you cannot find a clear semantic match,
   set refused=true — do not guess.

## Response format — return this JSON and nothing else

When a match is found:
{{
  "new_selector": "page.get_by_role(\\"button\\", name=\\"Sign In\\")",
  "confidence": 0.90,
  "reasoning": "The login form still exists; the submit button changed label from Submit to Sign In but serves the same purpose.",
  "refused": false,
  "refusal_reason": null
}}

When refusing:
{{
  "new_selector": null,
  "confidence": 0.0,
  "reasoning": "No submit-like button is present in the current DOM.",
  "refused": true,
  "refusal_reason": "Element type no longer exists on this page"
}}

Return JSON only.\
"""

# ---------------------------------------------------------------------------
# Reporter: all results → overall quality verdict
# ---------------------------------------------------------------------------

REPORTER_ANALYSIS_SYSTEM = """\
You are a senior QA engineer reviewing automated Playwright test results.
Give an honest, specific assessment of the application's test health.
Do not pad the analysis. Flag real concerns. Do not repeat the numbers
already in the report — add interpretation and actionable next steps.\
"""

REPORTER_ANALYSIS_PROMPT = """\
Review these automated test results and write a quality assessment.

**URL tested:** {url}
**Tests run:** {total} | **Passed:** {passed} ({pass_rate}%) | **Failed:** {failed}

## Flows and outcomes
{flows_summary}

## Failure details
{failures_summary}

Write your assessment in this format:

**Verdict:** Passing | Needs Attention | Critical Issues
<One sentence summarising overall health.>

**What is working:**
- <bullet per passing area — be specific about what user capability is confirmed>

**Areas of concern:**
- <bullet per failure — name the likely user impact, not just the technical error>

**Recommended next steps:**
1. <Most important action>
2. <Second action>
3. <Third action if warranted>

Stay under 300 words. Be specific to this application and these results.\
"""
