"""OpenAI (GPT) adapter."""

from __future__ import annotations

from .base import LLMProvider, ProviderAuthError, ProviderError, ProviderRateLimitError


class OpenAIProvider(LLMProvider):
    name = "openai"

    def _make_client(self):
        import openai

        return openai.OpenAI(api_key=self.api_key)

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str:
        import openai

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
        except openai.AuthenticationError as exc:
            raise ProviderAuthError("OpenAI API key is invalid or missing.") from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimitError("OpenAI rate limit hit — wait and retry.") from exc
        except openai.OpenAIError as exc:
            raise ProviderError(f"OpenAI API error: {exc}") from exc
        return (response.choices[0].message.content or "").strip()
