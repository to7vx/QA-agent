"""Symmetric encryption for secrets at rest (BYOK keys, auth storage states).

Uses Fernet (AES-128-CBC + HMAC). The key comes from ``QA_AGENT_SECRET_KEY``.
If no key is configured, a process-ephemeral key is generated so dev/tests work
— but secrets won't survive a restart, which is the intended loud failure mode
for a misconfigured production deploy.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("qa_agent.api.crypto")


class SecretBox:
    def __init__(self, key: str | None) -> None:
        if key:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
            self._ephemeral = False
        else:
            self._fernet = Fernet(Fernet.generate_key())
            self._ephemeral = True
            log.warning(
                "QA_AGENT_SECRET_KEY is not set — using an ephemeral encryption "
                "key. Stored secrets will NOT survive a restart."
            )

    @property
    def is_ephemeral(self) -> bool:
        return self._ephemeral

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, token: bytes | None) -> str | None:
        if not token:
            return None
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except InvalidToken:
            log.error("Failed to decrypt a stored secret (key rotated or corrupt).")
            return None


def generate_key() -> str:
    """Generate a fresh Fernet key (for ``QA_AGENT_SECRET_KEY``)."""
    return Fernet.generate_key().decode("ascii")
