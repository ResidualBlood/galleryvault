"""T5.1: migration 0045 creates ``duplicate_groups`` and backfills legacy state.

Uses a throwaway schema so the real test database is untouched. Skipped
automatically when no database is reachable (host runs); the container
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


def _load_migration_0045():
    for candidate in [
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "0045_duplicate_groups.py",
        Path("/app/alembic/versions/0045_duplicate_groups.py"),
    ]:
        if candidate.exists():
            spec = importlib.util.spec_from_file_location("migration_0045", candidate)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    msg = "0045_duplicate_groups.py not found"
    raise FileNotFoundError(msg)


migration_0045 = _load_migration_0045()


async def _run_migration(connection, schema_name, direction):
    def run(sync_conn):
        sync_conn.execute(text(f"SET search_path TO {schema_name}, public"))
        ctx = MigrationContext.configure(sync_conn)
        with Operations.context(ctx):
            getattr(migration_0045, direction)()

    await connection.run_sync(run)


@pytest.mark.asyncio
async def test_alembic_0045_duplicate_groups_table_and_backfill():
    db_url = get_settings().database_url
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database connection unavailable: {exc}")

    schema_name = f"test_mig_0045_{uuid.uuid4().hex[:8]}"
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"CREATE SCHEMA {schema_name}"))
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))
            await conn.execute(
                text(
                    "CREATE TABLE duplicate_records ("
                    "gid BIGINT PRIMARY KEY, status VARCHAR(16) NOT NULL, "
                    "policy VARCHAR(24) NOT NULL, winner_path TEXT, "
                    "copies JSONB NOT NULL, "
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                    "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                )
            )
            await conn.execute(
                text(
                    "CREATE TABLE favorite_duplicate_ignores ("
                    "key VARCHAR(512) PRIMARY KEY, title TEXT, gids JSONB, "
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO duplicate_records "
                    "(gid, status, policy, winner_path, copies) VALUES "
                    "(101, 'open', 'keep_first', '/lib/101', '[{\"path\": \"/lib/101\"}]'),"
                    "(102, 'resolved', 'keep_last', '/lib/102', "
                    "'[{\"path\": \"/lib/102\"}, {\"path\": \"/old/102\"}]'),"
                    "(103, 'dismissed', 'keep_first', NULL, '[]')"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO favorite_duplicate_ignores (key, title, gids) "
                    "VALUES ('artist|work', 'Work', '[7, 5]')"
                )
            )
            await conn.commit()

            await _run_migration(conn, schema_name, "upgrade")
            await conn.commit()
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))

            columns = (
                await conn.execute(
                    text(
                        "SELECT column_name, data_type, is_nullable "
                        "FROM information_schema.columns "
                        "WHERE table_schema = :schema AND table_name = 'duplicate_groups' "
                        "ORDER BY ordinal_position"
                    ),
                    {"schema": schema_name},
                )
            ).fetchall()
            assert [column[0] for column in columns] == [
                "id",
                "kind",
                "group_key",
                "status",
                "member_gids",
                "legacy_keys",
                "title",
                "artist",
                "payload",
                "present",
                "last_seen_at",
                "dismissed_at",
                "created_at",
                "updated_at",
            ]
            assert ("status", "character varying", "NO") in columns

            same_gid = (
                await conn.execute(
                    text(
                        "SELECT group_key, status, present, "
                        "member_gids = jsonb_build_array(group_key::bigint), "
                        "payload->>'policy', payload->>'winner_path', "
                        "(payload->'copies')::text "
                        "FROM duplicate_groups WHERE kind = 'same_gid' "
                        "ORDER BY group_key"
                    )
                )
            ).fetchall()
            assert [row[0] for row in same_gid] == ["101", "102", "103"]
            assert [row[1] for row in same_gid] == ["open", "dismissed", "dismissed"]
            assert all(row[2] is True for row in same_gid)
            assert all(row[3] is True for row in same_gid)
            assert [row[4] for row in same_gid] == ["keep_first", "keep_last", "keep_first"]
            assert [row[5] for row in same_gid] == ["/lib/101", "/lib/102", None]
            assert '"path": "/old/102"' in same_gid[1][6]

            dismissed_at = (
                await conn.execute(
                    text(
                        "SELECT group_key, dismissed_at IS NOT NULL "
                        "FROM duplicate_groups WHERE kind = 'same_gid' "
                        "ORDER BY group_key"
                    )
                )
            ).fetchall()
            assert dismissed_at == [("101", False), ("102", True), ("103", True)]

            ignored = (
                await conn.execute(
                    text(
                        "SELECT kind, group_key, status, present, "
                        "member_gids = '[5, 7]'::jsonb, title, "
                        "dismissed_at IS NOT NULL "
                        "FROM duplicate_groups WHERE group_key = 'artist|work' "
                        "ORDER BY kind"
                    )
                )
            ).fetchall()
            assert ignored == [
                ("cross_gid", "artist|work", "dismissed", False, True, "Work", True),
                ("favorites", "artist|work", "dismissed", False, True, "Work", True),
            ]

            # The legacy tables are kept intact until T5.3 switches the readers.
            legacy_counts = (
                await conn.execute(
                    text(
                        "SELECT (SELECT count(*) FROM duplicate_records), "
                        "(SELECT count(*) FROM favorite_duplicate_ignores)"
                    )
                )
            ).fetchone()
            assert legacy_counts == (3, 1)

            index_def = await conn.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = :schema "
                    "AND indexname = 'idx_duplicate_groups_kind_status_present'"
                ),
                {"schema": schema_name},
            )
            assert index_def is not None
            assert "(kind, status, present)" in index_def

            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(
                        "INSERT INTO duplicate_groups (kind, group_key) "
                        "VALUES ('other', 'x')"
                    )
                )
            await conn.rollback()
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))

            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(
                        "INSERT INTO duplicate_groups (kind, group_key) "
                        "VALUES ('same_gid', '101')"
                    )
                )
            await conn.rollback()
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))

            await _run_migration(conn, schema_name, "downgrade")
            await conn.commit()

            remaining = await conn.scalar(
                text("SELECT to_regclass(:qualified)"),
                {"qualified": f"{schema_name}.duplicate_groups"},
            )
            assert remaining is None
            legacy_after = (
                await conn.execute(
                    text(
                        "SELECT (SELECT count(*) FROM duplicate_records), "
                        "(SELECT count(*) FROM favorite_duplicate_ignores)"
                    )
                )
            ).fetchone()
            assert legacy_after == (3, 1)
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
        await engine.dispose()
