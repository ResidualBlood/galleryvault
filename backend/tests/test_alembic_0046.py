"""T7.4: migration 0046 creates ``task_runs`` and imports task history.

Uses a throwaway schema so the real test database is untouched.  Skipped
automatically when no database is reachable (host runs); the container
acceptance requires 0 skipped.
"""

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from galleryvault.config import get_settings


def _load_migration_0046():
    for candidate in [
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "0046_task_runs.py",
        Path("/app/alembic/versions/0046_task_runs.py"),
    ]:
        if candidate.exists():
            spec = importlib.util.spec_from_file_location("migration_0046", candidate)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    msg = "0046_task_runs.py not found"
    raise FileNotFoundError(msg)


migration_0046 = _load_migration_0046()


def test_revision_chain_is_fixed() -> None:
    assert migration_0046.revision == "0046_task_runs"
    assert migration_0046.down_revision == "0045_duplicate_groups"


async def _run_migration(connection, schema_name, direction):
    def run(sync_conn):
        sync_conn.execute(text(f"SET search_path TO {schema_name}, public"))
        ctx = MigrationContext.configure(sync_conn)
        with Operations.context(ctx):
            getattr(migration_0046, direction)()

    await connection.run_sync(run)


@pytest.mark.asyncio
async def test_alembic_0046_task_runs_table_and_history_backfill():
    db_url = get_settings().database_url
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database connection unavailable: {exc}")

    schema_name = f"test_mig_0046_{uuid.uuid4().hex[:8]}"
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"CREATE SCHEMA {schema_name}"))
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))
            await conn.execute(
                text(
                    "CREATE TABLE app_config ("
                    "key VARCHAR(64) PRIMARY KEY, "
                    "value JSONB NOT NULL, "
                    "updated_at TIMESTAMPTZ DEFAULT now())"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO app_config (key, value) VALUES "
                    "('task_history', CAST(:history AS jsonb))"
                ),
                {
                    "history": json.dumps({
                        "history": [
                            {
                                "task": "scan",
                                "started_at": "2026-11-13T10:00:00+00:00",
                                "completed_at": "2026-11-13T10:05:00+00:00",
                                "status": "success",
                                "reason": "",
                                "done": 42,
                                "total": 42,
                            },
                            {
                                "task": "favorites-check",
                                "started_at": "2026-11-13T11:00:00+00:00",
                                "completed_at": "2026-11-13T11:01:00+00:00",
                                "status": "failed",
                                "reason": "boom",
                                "done": 1,
                                "total": 2,
                            },
                            {
                                "task": "thumbs",
                                "started_at": None,
                                "completed_at": None,
                                "status": "cancelled",
                                "reason": "cancelled",
                                "done": 0,
                                "total": 0,
                            },
                            {
                                "task": "weird",
                                "started_at": "not-a-date",
                                "completed_at": "",
                                "status": "mystery",
                                "reason": "odd",
                                "done": "many",
                                "total": None,
                            },
                        ]
                    })
                },
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
                        "WHERE table_schema = :schema AND table_name = 'task_runs' "
                        "ORDER BY ordinal_position"
                    ),
                    {"schema": schema_name},
                )
            ).fetchall()
            assert [column[0] for column in columns] == [
                "id",
                "name",
                "run_id",
                "status",
                "stage",
                "cancellable",
                "done",
                "total",
                "last_error",
                "reason",
                "payload",
                "started_at",
                "completed_at",
                "heartbeat_at",
                "created_at",
                "updated_at",
            ]
            types = {row[0]: (row[1], row[2]) for row in columns}
            assert types["name"] == ("character varying", "NO")
            assert types["run_id"] == ("character varying", "NO")
            assert types["status"] == ("character varying", "NO")
            assert types["payload"] == ("jsonb", "NO")
            assert types["done"] == ("integer", "NO")
            assert types["cancellable"] == ("boolean", "NO")
            assert types["completed_at"] == ("timestamp with time zone", "YES")

            assert await conn.scalar(text("SELECT count(*) FROM task_runs")) == 4
            assert (
                await conn.scalar(text("SELECT count(DISTINCT run_id) FROM task_runs"))
                == 4
            )
            assert (
                await conn.scalar(
                    text("SELECT bool_and(length(run_id) = 36) FROM task_runs")
                )
                is True
            )

            rows = (
                await conn.execute(
                    text(
                        "SELECT name, status, done, total, reason, last_error, "
                        "payload = '{}'::jsonb, cancellable, "
                        "started_at IS NOT NULL, completed_at IS NOT NULL, "
                        "created_at IS NOT NULL "
                        "FROM task_runs ORDER BY name"
                    )
                )
            ).fetchall()
            assert rows == [
                ("favorites-check", "failed", 1, 2, "boom", "boom", True, False, True, True, True),
                ("scan", "success", 42, 42, None, None, True, False, True, True, True),
                ("thumbs", "cancelled", 0, 0, "cancelled", None, True, False, True, False, True),
                ("weird", "failed", 0, 0, "odd", "odd", True, False, True, False, True),
            ]

            running_index = await conn.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = :schema "
                    "AND indexname = 'idx_task_runs_running_name'"
                ),
                {"schema": schema_name},
            )
            assert running_index is not None
            assert "UNIQUE INDEX" in running_index
            assert "status" in running_index and "running" in running_index
            completed_index = await conn.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = :schema "
                    "AND indexname = 'idx_task_runs_name_completed'"
                ),
                {"schema": schema_name},
            )
            assert completed_index is not None
            assert "(name, completed_at DESC)" in completed_index

            # One running row per name, enforced by the partial unique index.
            await conn.execute(
                text(
                    "INSERT INTO task_runs (name, run_id) VALUES ('live', 'run-1')"
                )
            )
            await conn.commit()
            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(
                        "INSERT INTO task_runs (name, run_id) VALUES ('live', 'run-2')"
                    )
                )
            await conn.rollback()
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))

            # Finishing the live row releases the slot for a new run.
            await conn.execute(
                text(
                    "UPDATE task_runs SET status = 'success', completed_at = now() "
                    "WHERE name = 'live' AND status = 'running'"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO task_runs (name, run_id) VALUES ('live', 'run-2')"
                )
            )
            await conn.commit()
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM task_runs WHERE name = 'live'")
                )
                == 2
            )

            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(
                        "INSERT INTO task_runs (name, run_id, status) "
                        "VALUES ('bad-status', 'run-3', 'bogus')"
                    )
                )
            await conn.rollback()
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))

            await _run_migration(conn, schema_name, "downgrade")
            await conn.commit()

            remaining = await conn.scalar(
                text("SELECT to_regclass(:qualified)"),
                {"qualified": f"{schema_name}.task_runs"},
            )
            assert remaining is None
            history = await conn.scalar(
                text(
                    "SELECT value->'history' FROM "
                    f"{schema_name}.app_config WHERE key = 'task_history'"
                )
            )
            if isinstance(history, str):
                history = json.loads(history)
            assert history is not None and len(history) == 4
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
        await engine.dispose()
