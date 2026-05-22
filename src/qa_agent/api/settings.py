"""API service configuration (separate from the core agent ``Settings``)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    # Database. Sync URL is used by the repository (psycopg / sqlite).
    database_url: str = Field("sqlite:///qa_agent.db", alias="QA_AGENT_DATABASE_URL")

    # Fernet key (urlsafe base64, 32 bytes) used to encrypt BYOK provider keys
    # and auth-profile storage states at rest.
    secret_key: str | None = Field(None, alias="QA_AGENT_SECRET_KEY")

    # Supabase auth. The JWT secret verifies HS256 tokens minted by Supabase.
    supabase_jwt_secret: str | None = Field(None, alias="SUPABASE_JWT_SECRET")
    supabase_url: str | None = Field(None, alias="SUPABASE_URL")
    jwt_audience: str = Field("authenticated", alias="QA_AGENT_JWT_AUDIENCE")

    # CORS — comma-separated list of allowed dashboard origins.
    cors_origins: str = Field("http://localhost:3000", alias="QA_AGENT_CORS_ORIGINS")

    # Quotas / abuse control (per user, not global).
    max_concurrent_runs_per_user: int = Field(2, alias="QA_AGENT_MAX_CONCURRENT_RUNS")
    daily_run_cap_per_user: int = Field(50, alias="QA_AGENT_DAILY_RUN_CAP")
    parallelism: int = Field(4, alias="QA_AGENT_PARALLELISM")

    # Observability.
    log_level: str = Field("INFO", alias="QA_AGENT_LOG_LEVEL")
    log_json: bool = Field(True, alias="QA_AGENT_LOG_JSON")
    sentry_dsn: str | None = Field(None, alias="SENTRY_DSN")

    # Rate limiting (slowapi syntax, e.g. "120/minute"). Empty string disables.
    rate_limit: str = Field("120/minute", alias="QA_AGENT_RATE_LIMIT")
    rate_limit_runs: str = Field("20/minute", alias="QA_AGENT_RATE_LIMIT_RUNS")

    # Test/dev escape hatch: disable auth and treat every request as one user.
    auth_disabled: bool = Field(False, alias="QA_AGENT_AUTH_DISABLED")
    dev_user_id: str = Field("dev-user", alias="QA_AGENT_DEV_USER_ID")
    # When set, POST /runs blocks until the run completes (deterministic tests).
    run_inline: bool = Field(False, alias="QA_AGENT_RUN_INLINE")

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
