"""Per-user provider settings (Bring Your Own Key).

Keys are stored encrypted (Fernet) in ``user_settings`` and decrypted only in
memory when building a run's :class:`Settings`. The API process never mutates
global env (``LLMClient(mutate_env=False)``), so concurrent users' keys never
collide.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..config import Settings
from ..store.engine import Database
from ..store.models_orm import UserSettingsORM
from .crypto import SecretBox


class MissingProviderKeyError(Exception):
    """The user has no stored key matching the requested model's provider."""


def _provider_for_model(model: str) -> str:
    m = model.lower()
    if m.startswith("gemini/"):
        return "gemini"
    if m.startswith("anthropic/") or m.startswith("claude-"):
        return "anthropic"
    return "anthropic"


class UserSettingsService:
    def __init__(self, db: Database, box: SecretBox) -> None:
        self.db = db
        self.box = box

    def get_masked(self, owner_id: str) -> dict:
        """Return non-secret view of a user's settings for the dashboard."""
        with self.db.session() as s:
            row = s.get(UserSettingsORM, owner_id)
            if row is None:
                return {
                    "default_model": "anthropic/claude-sonnet-4-6",
                    "has_anthropic_key": False,
                    "has_gemini_key": False,
                    "updated_at": None,
                }
            return {
                "default_model": row.default_model,
                "has_anthropic_key": row.anthropic_key_encrypted is not None,
                "has_gemini_key": row.gemini_key_encrypted is not None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }

    def update(
        self,
        owner_id: str,
        *,
        anthropic_key: str | None = None,
        gemini_key: str | None = None,
        default_model: str | None = None,
        clear_anthropic: bool = False,
        clear_gemini: bool = False,
    ) -> dict:
        with self.db.session() as s:
            row = s.get(UserSettingsORM, owner_id)
            if row is None:
                row = UserSettingsORM(owner_id=owner_id)
                s.add(row)

            if anthropic_key:
                row.anthropic_key_encrypted = self.box.encrypt(anthropic_key.strip())
            elif clear_anthropic:
                row.anthropic_key_encrypted = None

            if gemini_key:
                row.gemini_key_encrypted = self.box.encrypt(gemini_key.strip())
            elif clear_gemini:
                row.gemini_key_encrypted = None

            if default_model:
                row.default_model = default_model
            row.updated_at = datetime.now(UTC)
        return self.get_masked(owner_id)

    def default_model(self, owner_id: str) -> str:
        with self.db.session() as s:
            row = s.get(UserSettingsORM, owner_id)
            return row.default_model if row else "anthropic/claude-sonnet-4-6"

    def build_run_settings(self, owner_id: str, *, model: str, headless: bool = True) -> Settings:
        """Construct a core :class:`Settings` carrying the user's decrypted key.

        Raises :class:`MissingProviderKeyError` if the user has no key for the
        model's provider.
        """
        provider = _provider_for_model(model)
        with self.db.session() as s:
            row = s.get(UserSettingsORM, owner_id)
            anthropic_blob = row.anthropic_key_encrypted if row else None
            gemini_blob = row.gemini_key_encrypted if row else None
            anthropic = self.box.decrypt(anthropic_blob)
            gemini = self.box.decrypt(gemini_blob)

        # Distinguish "no key stored" from "key stored but undecryptable" — the
        # latter happens when the server restarted without QA_AGENT_SECRET_KEY
        # (ephemeral key), and the generic "add a key" message is misleading.
        def _missing(
            prov: str, decrypted: str | None, blob: bytes | None
        ) -> MissingProviderKeyError:
            if blob is not None and not decrypted:
                return MissingProviderKeyError(
                    f"Your stored {prov} key could not be decrypted — the server is "
                    "running without QA_AGENT_SECRET_KEY, so saved keys don't survive a "
                    "restart. Set QA_AGENT_SECRET_KEY and re-enter your key on Settings."
                )
            return MissingProviderKeyError(
                f"No {prov} API key on file. Add one on the Settings page."
            )

        if provider == "anthropic" and not anthropic:
            raise _missing("Anthropic", anthropic, anthropic_blob)
        if provider == "gemini" and not gemini:
            raise _missing("Gemini", gemini, gemini_blob)

        return Settings(
            anthropic_api_key=anthropic,
            gemini_api_key=gemini,
            model=model,
            headless=headless,
        )
