"""B2/T2.1: ingest state columns, backfill and downgrade on real PostgreSQL.

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


def _load_migration_0043():
    for candidate in [
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "0043_download_ingest_state.py",
        Path("/app/alembic/versions/0043_download_ingest_state.py"),
    ]:
        if candidate.exists():
            spec = importlib.util.spec_from_file_location("migration_0043", candidate)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    msg = "0043_download_ingest_state.py not found"
    raise FileNotFoundError(msg)


migration_0043 = _load_migration_0043()


@pytest.mark.asyncio
async def test_alembic_0043_ingest_state_columns_and_backfill():
    db_url = get_settings().database_url
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database connection unavailable: {exc}")

    schema_name = f"test_mig_0043_{uuid.uuid4().hex[:8]}"
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"CREATE SCHEMA {schema_name}"))
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))
            await conn.execute(
                text(
                    "CREATE TABLE download_tasks ("
                    "id BIGSERIAL PRIMARY KEY, gid BIGINT, status VARCHAR(16))"
                )
            )
            await conn.execute(text("CREATE TABLE galleries (id BIGSERIAL PRIMARY KEY, gid BIGINT)"))
            await conn.execute(
                text(
                    "INSERT INTO galleries (gid) VALUES (90001);"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO download_tasks (gid, status) VALUES "
                    "(90001, 'success'), (90002, 'success'), (90003, 'downloading')"
                )
            )
            await conn.commit()

            def run_upgrade(sync_conn):
                sync_conn.execute(text(f"SET search_path TO {schema_name}, public"))
                ctx = MigrationContext.configure(sync_conn)
                with Operations.context(ctx):
                    migration_0043.upgrade()

            await conn.run_sync(run_upgrade)
            await conn.commit()
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))

            columns = (
                await conn.execute(
                    text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema = :schema AND table_name = 'download_tasks' "
                        "AND column_name IN ('ingest_status', 'ingest_payload')"
                    ),
                    {"schema": schema_name},
                )
            ).fetchall()
            assert ("ingest_status", "character varying") in columns
            assert ("ingest_payload", "jsonb") in columns

            rows = (
                await conn.execute(
                    text("SELECT gid, ingest_status FROM download_tasks ORDER BY gid")
                )
            ).fetchall()
            assert rows == [(90001, "done"), (90002, None), (90003, None)]

            index_predicate = await conn.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = :schema "
                    "AND indexname = 'idx_download_tasks_ingest_pending'"
                ),
                {"schema": schema_name},
            )
            assert index_predicate is not None
            assert "ingest_status" in index_predicate

            # The check constraint is enforced by the real database.
            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(
                        "INSERT INTO download_tasks (gid, status, ingest_status) "
                        "VALUES (90004, 'downloading', 'bogus')"
                    )
                )
            await conn.rollback()

            def run_downgrade(sync_conn):
                sync_conn.execute(text(f"SET search_path TO {schema_name}, public"))
                ctx = MigrationContext.configure(sync_conn)
                with Operations.context(ctx):
                    migration_0043.downgrade()

            await conn.run_sync(run_downgrade)
            await conn.commit()

            remaining = (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :schema AND table_name = 'download_tasks' "
                        "AND column_name IN ('ingest_status', 'ingest_payload')"
                    ),
                    {"schema": schema_name},
                )
            ).fetchall()
            assert remaining == []
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
        await engine.dispose()
