from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AppConfig
from .base import BaseRepository


class SettingsRepository(BaseRepository[AppConfig]):
    """Persistence for user-editable settings kept outside environment secrets."""

    KEY = "user_settings"
    EXTRA_KEY = "runtime_auth"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AppConfig)

    async def get(self) -> dict[str, Any]:
        row = await self.get_by_id(self.KEY)
        return dict(row.value) if row and row.value else {}

    async def save(self, value: dict[str, Any]) -> None:
        row = await self.get_by_id(self.KEY)
        if row is None:
            self.session.add(AppConfig(key=self.KEY, value=value))
        else:
            row.value = value
        await self.flush()

    async def save_extra(self, value: dict[str, Any]) -> None:
        """Persist non-editable runtime settings (e.g. a changed password hash).

        These are stored under their own key so they are never written to the
        config file and never show up in the editable settings payload.  The
        existing dict (which also holds ``auth_secret``) is merged, never
        replaced, so a password change does not invalidate session secrets.
        """
        row = await self.get_by_id(self.EXTRA_KEY)
        if row is None:
            self.session.add(AppConfig(key=self.EXTRA_KEY, value=value))
        else:
            merged = dict(row.value or {})
            merged.update(value)
            row.value = merged
        await self.flush()

    async def get_extra(self) -> dict[str, Any]:
        """Fetch non-editable runtime settings (e.g. runtime_auth)."""
        row = await self.get_by_id(self.EXTRA_KEY)
        return dict(row.value) if row and row.value else {}

    async def get_config(self, key: str) -> Any | None:
        """Fetch generic configuration by key."""
        row = await self.get_by_id(key)
        return row.value if row else None

    async def set_config(self, key: str, value: Any) -> None:
        """Upsert generic configuration by key."""
        row = await self.get_by_id(key)
        if row is None:
            self.session.add(AppConfig(key=key, value=value))
        else:
            row.value = value
        await self.flush()

    async def get_all_configs(self) -> dict[str, Any]:
        """Retrieve all configuration records as a key-value dictionary."""
        rows = await self.list_all()
        return {r.key: r.value for r in rows if r.key}
