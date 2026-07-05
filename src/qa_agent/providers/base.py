"""Provider-agnostic LLM interface and error types.

Every module in qa_agent talks to an LLM the same way: a system prompt plus a
user prompt in, text out. Adapters map each vendor SDK onto this interface and
translate SDK-specific exceptions into the ProviderError hierarchy so callers
never import a vendor SDK directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderError(Exception):
    """Base error for any LLM provider failure."""


class ProviderAuthError(ProviderError):
    """API key is missing, invalid, or lacks permission."""


class ProviderRateLimitError(ProviderError):
    """Provider rate limit hit — retry later."""


class LLMProvider(ABC):
    """Minimal completion interface shared by all provider adapters."""

    name: str = ""

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key
        self._client = None  # built lazily on first use

    @abstractmethod
    def _make_client(self):
        """Import the vendor SDK and construct its client."""

    @property
    def client(self):
        if self._client is None:
            self._client = self._make_client()
        return self._client

    @abstractmethod
    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str:
        """Run one completion: system + user prompt -> response text."""
