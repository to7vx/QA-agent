"""Provider catalog and factory.

The model lists are suggestions surfaced in the dashboard UI — the model field
always accepts free text, so a stale catalog never blocks anyone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import LLMProvider, ProviderError


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    key_env: str
    models: list[str] = field(default_factory=list)
    default_model: str = ""


PROVIDERS: dict[str, ProviderInfo] = {
    "anthropic": ProviderInfo(
        id="anthropic",
        label="Claude (Anthropic)",
        key_env="ANTHROPIC_API_KEY",
        models=["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"],
        default_model="claude-sonnet-4-6",
    ),
    "openai": ProviderInfo(
        id="openai",
        label="GPT (OpenAI)",
        key_env="OPENAI_API_KEY",
        models=["gpt-5.1", "gpt-5", "gpt-5-mini"],
        default_model="gpt-5.1",
    ),
    "google": ProviderInfo(
        id="google",
        label="Gemini (Google)",
        key_env="GOOGLE_API_KEY",
        models=["gemini-2.5-pro", "gemini-2.5-flash"],
        default_model="gemini-2.5-pro",
    ),
}


def create_provider(provider_id: str, model: str, api_key: str) -> LLMProvider:
    info = PROVIDERS.get(provider_id)
    if info is None:
        raise ProviderError(
            f"Unknown provider '{provider_id}'. Choose one of: {', '.join(PROVIDERS)}"
        )

    resolved_model = model or info.default_model

    if provider_id == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=resolved_model, api_key=api_key)
    if provider_id == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(model=resolved_model, api_key=api_key)

    from .google_provider import GoogleProvider

    return GoogleProvider(model=resolved_model, api_key=api_key)
