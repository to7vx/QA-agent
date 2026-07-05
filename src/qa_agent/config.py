"""Configuration loaded from environment variables.

Provider API keys are all optional here — at least one must be available
(via env, .env, or the dashboard keystore) by the time a run starts, and
that check happens at the call site, not at Settings construction.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    google_api_key: str | None = Field(None, alias="GOOGLE_API_KEY")
    provider: str = Field("anthropic", alias="QA_AGENT_PROVIDER")
    model: str = Field("claude-sonnet-4-6", alias="QA_AGENT_MODEL")
    headless: bool = Field(True, alias="QA_AGENT_HEADLESS")
    output_dir: Path = Field(Path("generated_tests"), alias="QA_AGENT_OUTPUT_DIR")
    report_dir: Path = Field(Path("reports"), alias="QA_AGENT_REPORT_DIR")

    model_config = {"populate_by_name": True, "extra": "ignore"}

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
