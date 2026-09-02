from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AppConfig


class SettingsRepository:
    """Persistence for user-editable settings kept outside environment secrets."""

    KEY = "user_settings"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self) -> dict:
        row = await self.session.get(AppConfig, self.KEY)
        return dict(row.value) if row else {}

    async def save(self, value: dict) -> None:
        row = await self.session.get(AppConfig, self.KEY)
        if row is None:
            self.session.add(AppConfig(key=self.KEY, value=value))
        else:
            row.value = value
        await self.session.flush()

    async def save_extra(self, value: dict) -> None:
        """Persist non-editable runtime settings (e.g. a changed password hash).

        These are stored under their own key so they are never written to the
        config file and never show up in the editable settings payload.  The
        existing dict (which also holds ``auth_secret``) is merged, never
        replaced, so a password change does not invalidate session secrets.
        """
        row = await self.session.get(AppConfig, "runtime_auth")
        if row is None:
            self.session.add(AppConfig(key="runtime_auth", value=value))
        else:
            merged = dict(row.value or {})
            merged.update(value)
            row.value = merged
        await self.session.flush()
