# QA Agent

An autonomous AI-powered browser testing agent. Given a URL, it:

1. **Explores** the page with Playwright and identifies user flows via Claude
2. **Generates** Playwright test cases (Python) for each flow
3. **Executes** the tests and collects results
4. **Reports** findings as a structured Markdown report

## Stack

| Tool | Purpose |
|------|---------|
| [Claude](https://anthropic.com) (`claude-sonnet-4-6`) | Flow identification + test generation |
| [Playwright](https://playwright.dev/python/) | Browser automation |
| [Pydantic](https://docs.pydantic.dev/) | Typed domain models |
| [Rich](https://rich.readthedocs.io/) | CLI output |
| [uv](https://docs.astral.sh/uv/) | Package management |
| pytest | Testing the agent itself |

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Install Playwright browsers

```bash
uv run playwright install chromium
```

### 3. Configure environment

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
```

## Usage

```bash
uv run qa-agent run https://example.com
```

Options:

```
--headed        Run browser in visible window (default: headless)
--model TEXT    Override Claude model (default: claude-sonnet-4-6)
```

## Project Structure

```
src/qa_agent/
├── agent.py       # Main orchestrator
├── explorer.py    # Playwright page capture + Claude flow identification
├── generator.py   # Claude test case generation
├── executor.py    # pytest runner
├── reporter.py    # Markdown report + Rich CLI output
├── models.py      # Pydantic types: Flow, TestCase, TestResult, Report
├── prompts.py     # Claude prompt templates
├── config.py      # Settings via python-dotenv
└── cli.py         # Click CLI entry point

generated_tests/   # AI-generated Playwright test files (auto-created)
reports/           # Markdown reports (auto-created)
tests/             # Unit tests for the agent itself
```

## Running Tests

```bash
uv run pytest
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `QA_AGENT_MODEL` | `claude-sonnet-4-6` | Claude model to use |
| `QA_AGENT_HEADLESS` | `true` | Headless browser mode |
| `QA_AGENT_OUTPUT_DIR` | `generated_tests` | Generated test output directory |
| `QA_AGENT_REPORT_DIR` | `reports` | Report output directory |
