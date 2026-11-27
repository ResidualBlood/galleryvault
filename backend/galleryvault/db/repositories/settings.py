from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import ARRAY, Text, func, literal, select
from sqlalchemy.dialects.postgresql import insert
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

    @staticmethod
    def patch_statement(changes: Mapping[str, Any], remove: Sequence[str] = ()) -> Any:
        """Build the atomic partial update for ``user_settings``.

        The table holds one JSONB document per key, so a partial change must be
        merged in the database: ``value = (value || excluded.value) - remove``.
        Read-modify-write from Python loses concurrent updates (one writer
        overwrites keys it never touched) and races on the first insert.
        """
        stmt = insert(AppConfig).values(key=SettingsRepository.KEY, value=dict(changes))
        merged = AppConfig.value.concat(stmt.excluded.value)
        removed = [str(key) for key in remove]
        if removed:
            # ``jsonb - text[]`` removes each named *top-level* key.  ``#-``
            # would instead treat the list as one nested path (a.b), which is
            # wrong as soon as more than one key is requested.  Parenthesise the
            # merge: binary ``-`` binds tighter than ``||`` in PostgreSQL.
            merged = merged.self_group().op("-")(literal(removed, type_=ARRAY(Text)))
        return stmt.on_conflict_do_update(
            index_elements=[AppConfig.key],
            set_={"value": merged, "updated_at": func.now()},
        )

    async def patch(self, changes: Mapping[str, Any], remove: Sequence[str] = ()) -> None:
        """Atomically merge ``changes`` into ``user_settings`` and drop ``remove`` keys.

        Only the keys named by the caller are written; any other persisted key
        (notably encrypted cookies/tokens) is left byte-for-byte untouched.
        """
        if not changes and not remove:
            return
        await self.session.execute(self.patch_statement(changes, remove))

    async def get_for_update(self) -> dict[str, Any]:
        """Read ``user_settings`` under a row lock.

        ``SELECT ... FOR UPDATE`` serialises concurrent read-modify-write cycles
        (e.g. two tabs adding a saved search at the same time), which otherwise
        lose updates because each request read the same snapshot.
        """
        # A missing row cannot be locked. Seed it atomically before taking the
        # lock; concurrent first writers wait on the same unique key instead of
        # racing an INSERT.
        await self.session.execute(
            insert(AppConfig)
            .values(key=self.KEY, value={})
            .on_conflict_do_nothing(index_elements=[AppConfig.key])
        )
        stmt = (
            select(AppConfig)
            .where(AppConfig.key == self.KEY)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return dict(row.value) if row is not None and row.value else {}

    async def replace_all(self, value: dict[str, Any]) -> None:
        """Replace the whole ``user_settings`` document.

        Reserved for explicit import/reset flows.  Normal write paths must use
        :meth:`patch` so unrelated keys are never clobbered.
        """
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

async def patch_settings(repo: Any, changes: Mapping[str, Any], remove: Sequence[str] = ()) -> None:
    """Apply a partial ``user_settings`` update through ``repo``.

    The production repository takes the atomic upsert path (``repo.patch``).
    Repository doubles used by older router tests only implement ``get``/
    ``save``; they fall back to a read-modify-write so those tests keep
    exercising the router logic unchanged.
    """
    patcher = getattr(repo, "patch", None)
    if callable(patcher):
        await patcher(changes, remove=remove)
        return
    merged = {**(await repo.get()), **changes}
    for key in remove:
        merged.pop(key, None)
    await repo.save(merged)
