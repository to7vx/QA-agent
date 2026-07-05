"""Local API key store: ~/.qa-agent/config.json.

Keys entered in the dashboard are stored here in plaintext — the accepted
trade-off for a local single-user tool (documented in the README). Environment
variables remain a fallback so CI/power users never need the file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .providers.registry import PROVIDERS

_DEFAULTS = {"provider": "anthropic", "model": "claude-sonnet-4-6"}


class KeyStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path.home() / ".qa-agent" / "config.json"

    # ------------------------------------------------------------------
    # Keys
    # ------------------------------------------------------------------

    def get_key(self, provider: str) -> str | None:
        key = self._load().get("keys", {}).get(provider)
        if key:
            return key
        info = PROVIDERS.get(provider)
        if info is not None:
            return os.environ.get(info.key_env) or None
        return None

    def set_key(self, provider: str, key: str) -> None:
        data = self._load()
        data.setdefault("keys", {})[provider] = key
        self._save(data)

    def delete_key(self, provider: str) -> None:
        data = self._load()
        data.get("keys", {}).pop(provider, None)
        self._save(data)

    def mask(self, provider: str) -> str | None:
        key = self.get_key(provider)
        if not key:
            return None
        return f"{key[:3]}…{key[-4:]}" if len(key) > 8 else "…"

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    def get_defaults(self) -> dict:
        stored = self._load().get("defaults", {})
        return {**_DEFAULTS, **stored}

    def set_defaults(self, provider: str, model: str) -> None:
        data = self._load()
        data["defaults"] = {"provider": provider, "model": model}
        self._save(data)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)  # best-effort on Windows
        except OSError:
            pass
