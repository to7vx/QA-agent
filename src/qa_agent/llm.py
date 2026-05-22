"""Provider-agnostic LLM client backed by LiteLLM.

Model strings follow LiteLLM conventions:
    - Anthropic: "anthropic/claude-sonnet-4-6" (or bare "claude-sonnet-4-6")
    - Gemini:    "gemini/gemini-2.0-flash"

API keys are read from environment variables by LiteLLM directly
(ANTHROPIC_API_KEY, GEMINI_API_KEY).
"""

from __future__ import annotations

import logging
import os

# Silence LiteLLM's AWS-provider preload warnings before import — we don't
# ship botocore, and the noise is irrelevant when using Anthropic/Gemini.
logging.getLogger("LiteLLM").setLevel(logging.ERROR)

import litellm  # noqa: E402
from litellm.exceptions import (  # noqa: E402
    APIError,
    AuthenticationError,
    RateLimitError,
)

from .config import Settings  # noqa: E402  (after LiteLLM log-level setup, intentional)

__all__ = ["LLMClient", "AuthenticationError", "RateLimitError", "APIError"]


class LLMClient:
    def __init__(self, settings: Settings, *, mutate_env: bool = True) -> None:
        self.settings = settings
        self.model = settings.model

        # Mirror keys into the environment as a fallback (some LiteLLM code
        # paths rely on it). We also pass api_key explicitly per request,
        # because env-var pickup can be shadowed by other Google creds
        # (e.g. GOOGLE_API_KEY, GOOGLE_APPLICATION_CREDENTIALS) on the host.
        #
        # The long-lived API process must NOT mutate global env per request —
        # concurrent users bring their own (BYOK) keys, and a shared env var
        # would let one user's key bleed into another's run. The API passes
        # mutate_env=False; keys still flow through `complete()`'s explicit
        # api_key argument, which is per-instance and concurrency-safe.
        if mutate_env:
            if settings.anthropic_api_key:
                os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
            if settings.gemini_api_key:
                os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

        litellm.suppress_debug_info = True

    def _api_key_for(self, model: str) -> str | None:
        m = model.lower()
        if m.startswith("gemini/"):
            return self.settings.gemini_api_key
        if m.startswith("anthropic/") or m.startswith("claude-"):
            return self.settings.anthropic_api_key
        return None  # let LiteLLM figure it out for other providers

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4_096,
        model: str | None = None,
    ) -> str:
        """Send a single-turn system+user prompt and return the response text."""
        chosen_model = model or self.model
        response = litellm.completion(
            model=chosen_model,
            api_key=self._api_key_for(chosen_model),
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""
