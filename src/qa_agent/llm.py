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

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

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
from .models import Usage  # noqa: E402
from .pricing import estimate_cost  # noqa: E402

log = logging.getLogger("qa_agent.llm")

__all__ = ["LLMClient", "AuthenticationError", "RateLimitError", "APIError"]


def _is_transient(exc: BaseException) -> bool:
    """Retry rate limits and transient (5xx) API errors; never auth failures."""
    if isinstance(exc, AuthenticationError):
        return False
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIError):
        status = getattr(exc, "status_code", None)
        # Retry server-side and unknown failures; not 4xx client errors.
        return status is None or status >= 500
    return False


class LLMClient:
    def __init__(self, settings: Settings, *, mutate_env: bool = True) -> None:
        self.settings = settings
        self.model = settings.model
        # Cumulative token/cost usage across this client's lifetime. The API
        # creates one client per run, so this is effectively per-run usage;
        # the pipeline never has to thread usage through each stage.
        self.usage = Usage()

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

    @retry(
        retry=retry_if_exception(_is_transient),
        wait=wait_exponential_jitter(initial=1, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _completion(self, *, model: str, max_tokens: int, messages: list[dict]):
        return litellm.completion(
            model=model,
            api_key=self._api_key_for(model),
            max_tokens=max_tokens,
            messages=messages,
        )

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4_096,
        model: str | None = None,
    ) -> str:
        """Send a single-turn system+user prompt and return the response text.

        Transient failures (rate limits, 5xx) are retried with exponential
        backoff; auth failures fail fast. Token usage + estimated cost are
        accumulated on ``self.usage``.
        """
        chosen_model = model or self.model
        response = self._completion(
            model=chosen_model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        self._record_usage(chosen_model, response)
        return response.choices[0].message.content or ""

    def _record_usage(self, model: str, response: object) -> None:
        """Best-effort token/cost accounting; never break a run over telemetry."""
        try:
            usage = getattr(response, "usage", None)
            tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
            tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
            self.usage.add(
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=estimate_cost(model, tokens_in, tokens_out),
            )
        except Exception:  # pragma: no cover - defensive
            log.debug("Failed to record LLM usage", exc_info=True)
