"""Google (Gemini) adapter."""

from __future__ import annotations

from .base import LLMProvider, ProviderAuthError, ProviderError, ProviderRateLimitError


class GoogleProvider(LLMProvider):
    name = "google"

    def _make_client(self):
        from google import genai

        return genai.Client(api_key=self.api_key)

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str:
        try:
            from google.genai import errors as genai_errors
        except ImportError:  # pragma: no cover - SDK always ships errors module
            genai_errors = None

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "system_instruction": system,
                    "max_output_tokens": max_tokens,
                },
            )
        except Exception as exc:
            if genai_errors is not None and isinstance(exc, genai_errors.APIError):
                code = getattr(exc, "code", None)
                if code in (401, 403):
                    raise ProviderAuthError("Google API key is invalid or missing.") from exc
                if code == 429:
                    raise ProviderRateLimitError("Google rate limit hit — wait and retry.") from exc
                raise ProviderError(f"Google API error: {exc}") from exc
            raise ProviderError(f"Google API error: {exc}") from exc
        return (response.text or "").strip()
