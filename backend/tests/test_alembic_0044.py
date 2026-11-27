"""T4.1: migration 0044 adds ``storage_tier``/``cold_at`` and the cold index.

Skipped automatically when no database is reachable (host runs); the container
acceptance requires 0 skipped.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from galleryvault.config import get_settings


def _load_migration_0044():
    for candidate in [
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "0044_gallery_storage_tier.py",
        Path("/app/alembic/versions/0044_gallery_storage_tier.py"),
    ]:
        if candidate.exists():
            spec = importlib.util.spec_from_file_location("migration_0044", candidate)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    msg = "0044_gallery_storage_tier.py not found"
    raise FileNotFoundError(msg)


migration_0044 = _load_migration_0044()


@pytest.mark.asyncio
async def test_alembic_0044_storage_tier_columns_and_backfill():
    db_url = get_settings().database_url
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database connection unavailable: {exc}")

    schema_name = f"test_mig_0044_{uuid.uuid4().hex[:8]}"
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"CREATE SCHEMA {schema_name}"))
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))
            await conn.execute(
                text("CREATE TABLE galleries (id BIGSERIAL PRIMARY KEY, storage_path TEXT)")
            )
            await conn.execute(
                text("INSERT INTO galleries (storage_path) VALUES ('/downloads/1-old')")
            )
            await conn.commit()

            def run_upgrade(sync_conn):
                sync_conn.execute(text(f"SET search_path TO {schema_name}, public"))
                ctx = MigrationContext.configure(sync_conn)
                with Operations.context(ctx):
                    migration_0044.upgrade()

            await conn.run_sync(run_upgrade)
            await conn.commit()
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))

            columns = (
                await conn.execute(
                    text(
                        "SELECT column_name, data_type, is_nullable, column_default "
                        "FROM information_schema.columns "
                        "WHERE table_schema = :schema AND table_name = 'galleries' "
                        "AND column_name IN ('storage_tier', 'cold_at') "
                        "ORDER BY column_name"
                    ),
                    {"schema": schema_name},
                )
            ).fetchall()
            assert columns == [
                ("cold_at", "timestamp with time zone", "YES", None),
                ("storage_tier", "character varying", "NO", "'hot'::character varying"),
            ]

            # Existing rows are backfilled with the default; reconcile (runtime
            # cold roots) is what later flips genuinely cold rows.
            row = (
                await conn.execute(text("SELECT storage_tier, cold_at FROM galleries"))
            ).fetchone()
            assert row == ("hot", None)

            index_def = await conn.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = :schema "
                    "AND indexname = 'idx_galleries_storage_tier_cold'"
                ),
                {"schema": schema_name},
            )
            assert index_def is not None
            assert "storage_tier" in index_def
            assert "WHERE" in index_def.upper()

            # The check constraint is enforced by the real database.
            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(
                        "INSERT INTO galleries (storage_path, storage_tier) "
                        "VALUES ('/downloads/2', 'warm')"
                    )
                )
            await conn.rollback()
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))

            def run_downgrade(sync_conn):
                sync_conn.execute(text(f"SET search_path TO {schema_name}, public"))
                ctx = MigrationContext.configure(sync_conn)
                with Operations.context(ctx):
                    migration_0044.downgrade()

            await conn.run_sync(run_downgrade)
            await conn.commit()

            remaining = (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :schema AND table_name = 'galleries' "
                        "AND column_name IN ('storage_tier', 'cold_at')"
                    ),
                    {"schema": schema_name},
                )
            ).fetchall()
            assert remaining == []
            index_after = await conn.scalar(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = :schema "
                    "AND indexname = 'idx_galleries_storage_tier_cold'"
                ),
                {"schema": schema_name},
            )
            assert index_after is None
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
        await engine.dispose()
