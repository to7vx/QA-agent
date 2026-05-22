"""Configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # Provider keys — at least one must be set, matching the chosen model.
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")

    # LiteLLM model string. Examples:
    #   anthropic/claude-sonnet-4-6
    #   anthropic/claude-haiku-4-5-20251001
    #   gemini/gemini-2.0-flash
    model: str = Field("anthropic/claude-sonnet-4-6", alias="QA_AGENT_MODEL")
    headless: bool = Field(True, alias="QA_AGENT_HEADLESS")
    output_dir: Path = Field(Path("generated_tests"), alias="QA_AGENT_OUTPUT_DIR")
    report_dir: Path = Field(Path("reports"), alias="QA_AGENT_REPORT_DIR")

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @model_validator(mode="after")
    def _check_provider_key(self) -> Settings:
        m = self.model.lower()
        if m.startswith("gemini/") and not self.gemini_api_key:
            raise ValueError(f"QA_AGENT_MODEL={self.model} but GEMINI_API_KEY is not set.")
        if (m.startswith("anthropic/") or m.startswith("claude-")) and not self.anthropic_api_key:
            raise ValueError(f"QA_AGENT_MODEL={self.model} but ANTHROPIC_API_KEY is not set.")
        return self

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
