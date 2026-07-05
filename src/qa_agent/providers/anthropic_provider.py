"""Anthropic (Claude) adapter."""

from __future__ import annotations

from .base import LLMProvider, ProviderAuthError, ProviderError, ProviderRateLimitError


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def _make_client(self):
        import anthropic

        return anthropic.Anthropic(api_key=self.api_key)

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str:
        import anthropic

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError as exc:
            raise ProviderAuthError("Anthropic API key is invalid or missing.") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimitError("Anthropic rate limit hit — wait and retry.") from exc
        except anthropic.APIError as exc:
            raise ProviderError(f"Anthropic API error: {exc}") from exc
        return response.content[0].text.strip()
