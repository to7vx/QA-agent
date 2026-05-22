"""Owner-scoped auth-profile storage (encrypted Playwright storage states)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from ..models import AuthProfile
from ..store.engine import Database
from ..store.models_orm import AuthProfileORM
from .crypto import SecretBox


class AuthProfileService:
    def __init__(self, db: Database, box: SecretBox) -> None:
        self.db = db
        self.box = box

    def create(
        self, owner_id: str, *, name: str, origin: str, storage_state: dict[str, Any]
    ) -> dict:
        pid = "auth_" + uuid.uuid4().hex[:12]
        blob = self.box.encrypt(json.dumps(storage_state))
        with self.db.session() as s:
            s.add(
                AuthProfileORM(
                    id=pid,
                    owner_id=owner_id,
                    name=name,
                    origin=origin,
                    storage_state_encrypted=blob,
                    created_at=datetime.now(UTC),
                )
            )
        return {"id": pid, "name": name, "origin": origin}

    def list(self, owner_id: str) -> list[dict]:
        from sqlalchemy import select

        with self.db.session() as s:
            rows = (
                s.execute(
                    select(AuthProfileORM)
                    .where(AuthProfileORM.owner_id == owner_id)
                    .order_by(AuthProfileORM.created_at.desc())
                )
                .scalars()
                .all()
            )
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "origin": r.origin,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                }
                for r in rows
            ]

    def delete(self, owner_id: str, profile_id: str) -> bool:
        with self.db.session() as s:
            row = s.get(AuthProfileORM, profile_id)
            if row is None or row.owner_id != owner_id:
                return False
            s.delete(row)
            return True

    def load(self, owner_id: str, profile_id: str) -> AuthProfile | None:
        """Decrypt and return a profile (for run execution). Owner-scoped."""
        with self.db.session() as s:
            row = s.get(AuthProfileORM, profile_id)
            if row is None or row.owner_id != owner_id:
                return None
            raw = self.box.decrypt(row.storage_state_encrypted)
            state = json.loads(raw) if raw else {}
            return AuthProfile(
                id=row.id,
                name=row.name,
                origin=row.origin,
                storage_state=state,
                created_at=row.created_at,
                expires_at=row.expires_at,
            )
