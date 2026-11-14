"""T6.3: real-PostgreSQL atomic ``user_settings`` patch.

Each test creates a throwaway schema with a minimal ``app_config`` table so the
shared test database and the running backend are never touched.  Skipped on the
host (no PostgreSQL), required (0 skipped) in the test container.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from galleryvault.config import get_settings
from galleryvault.db.models import AppConfig
from galleryvault.db.repositories.settings import SettingsRepository


class _Schema:
    def __init__(self, name: str, engine: AsyncEngine) -> None:
        self.name = name
        self.engine = engine
        self.factory = async_sessionmaker(engine, expire_on_commit=False)

    def other_engine(self) -> AsyncEngine:
        return _schema_engine(self.name)

    def other_factory(self) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(self.other_engine(), expire_on_commit=False)


def _schema_engine(schema: str) -> AsyncEngine:
    return create_async_engine(
        get_settings().database_url,
        connect_args={"server_settings": {"search_path": f"{schema},public"}},
    )


@asynccontextmanager
async def _schema() -> AsyncIterator[_Schema]:
    db_url = get_settings().database_url
    probe = create_async_engine(db_url)
    try:
        async with probe.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        await probe.dispose()
        pytest.skip(f"Database connection unavailable: {exc}")

    name = f"t63_settings_{uuid.uuid4().hex[:10]}"
    async with probe.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {name}"))
        await conn.execute(
            text(
                f"""
                CREATE TABLE {name}.app_config (
                    key VARCHAR(64) PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
        )
    engine = _schema_engine(name)
    try:
        yield _Schema(name, engine)
    finally:
        await engine.dispose()
        async with probe.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA {name} CASCADE"))
        await probe.dispose()


async def _rows(schema: _Schema) -> int:
    async with schema.factory() as session:
        return int(await session.scalar(select(func.count()).select_from(AppConfig)) or 0)


@pytest.mark.asyncio
async def test_concurrent_patch_of_different_keys_keeps_both_last_writes() -> None:
    async with _schema() as schema:
        other = schema.other_factory()

        async def writer(factory: async_sessionmaker[AsyncSession], key: str) -> None:
            for i in range(50):
                async with factory() as session:
                    await SettingsRepository(session).patch({key: i})
                    await session.commit()

        # The table starts empty: both writers race the very first INSERT.
        await asyncio.gather(
            writer(schema.factory, "left"),
            writer(other, "right"),
        )

        async with schema.factory() as session:
            stored = await SettingsRepository(session).get()
        assert stored["left"] == 49
        assert stored["right"] == 49
        assert await _rows(schema) == 1


@pytest.mark.asyncio
async def test_patch_only_rewrites_the_keys_it_names() -> None:
    async with _schema() as schema:
        async with schema.factory() as session:
            await SettingsRepository(session).patch(
                {
                    "exhentai_cookies": {"ipb_member_id": "enc"},
                    "saved_searches": [{"id": "keep"}],
                    "title_display": "japanese",
                }
            )
            await session.commit()

        async with schema.factory() as session:
            await SettingsRepository(session).patch(
                {"saved_searches": []}, remove=("saved_searches",)
            )
            await session.commit()

        async with schema.factory() as session:
            stored = await SettingsRepository(session).get()
        assert "saved_searches" not in stored
        # Keys absent from the patch are never rewritten (encrypted values stay).
        assert stored["exhentai_cookies"] == {"ipb_member_id": "enc"}
        assert stored["title_display"] == "japanese"


@pytest.mark.asyncio
async def test_patch_remove_drops_multiple_top_level_keys() -> None:
    async with _schema() as schema:
        async with schema.factory() as session:
            await SettingsRepository(session).patch({"a": 1, "b": 2, "c": 3})
            await session.commit()

        async with schema.factory() as session:
            await SettingsRepository(session).patch({}, remove=["a", "b"])
            await session.commit()

        async with schema.factory() as session:
            stored = await SettingsRepository(session).get()
        # ``jsonb #- '{a,b}'`` would have searched for a nested a.b and kept
        # both top-level keys; only ``jsonb - text[]`` drops each of them.
        assert stored == {"c": 3}


@pytest.mark.asyncio
async def test_get_for_update_seeds_missing_row_and_locks_it() -> None:
    async with _schema() as schema:
        async with schema.factory() as session:
            repo = SettingsRepository(session)
            assert await repo.get_for_update() == {}
            await session.commit()

        assert await _rows(schema) == 1

        async with schema.factory() as session:
            repo = SettingsRepository(session)
            await repo.patch({"title_display": "english"})
            await session.commit()

        async with schema.factory() as session:
            stored = await SettingsRepository(session).get_for_update()
            assert stored == {"title_display": "english"}
            await session.rollback()
