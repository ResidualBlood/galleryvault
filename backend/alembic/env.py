import asyncio
import logging
import os
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from galleryvault.config import get_settings
from galleryvault.db.models import Base

logger = logging.getLogger(__name__)

# Session-level PostgreSQL advisory lock shared by every replica that runs
# ``alembic upgrade head`` from entrypoint.sh.  0x47564D4947524154 is
# "GVMIGRAT" in ASCII and fits in a signed 64-bit integer.
ADVISORY_LOCK_KEY = 0x47564D4947524154
# Wait cap for acquiring the lock, in seconds.  Overridable per invocation
# (e.g. ``GALLERYVAULT_MIGRATION_LOCK_TIMEOUT=3 alembic upgrade head``).
LOCK_TIMEOUT_ENV = "GALLERYVAULT_MIGRATION_LOCK_TIMEOUT"
DEFAULT_LOCK_TIMEOUT_SECONDS = 120.0

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def _lock_timeout_seconds() -> float:
    """Return the configured advisory-lock wait cap in seconds."""
    raw = os.environ.get(LOCK_TIMEOUT_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_LOCK_TIMEOUT_SECONDS
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"Migration lock timeout ({LOCK_TIMEOUT_ENV}={raw!r}) must be a number"
        ) from exc
    if seconds <= 0:
        raise RuntimeError(
            f"Migration lock timeout ({LOCK_TIMEOUT_ENV}={raw!r}) must be positive"
        )
    return seconds


def _advisory_lock_sql() -> str:
    return f"SELECT pg_advisory_lock({ADVISORY_LOCK_KEY})"


def _advisory_unlock_sql() -> str:
    return f"SELECT pg_advisory_unlock({ADVISORY_LOCK_KEY})"


def _is_timeout_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "statement timeout" in message or "lock timeout" in message


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    lock_timeout_ms = max(1, int(_lock_timeout_seconds() * 1000))
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # Both GUCs are applied at connection startup.  ``lock_timeout``
        # covers ordinary lock waits; ``statement_timeout`` is what reliably
        # aborts a blocked ``pg_advisory_lock`` (a long-running function call).
        connect_args={
            "server_settings": {
                "lock_timeout": str(lock_timeout_ms),
                "statement_timeout": str(lock_timeout_ms),
            }
        },
    )

    async def run() -> None:
        async with connectable.connect() as connection:
            try:
                await connection.execute(text(_advisory_lock_sql()))
            except Exception as exc:
                if _is_timeout_error(exc):
                    raise RuntimeError(
                        "Timed out waiting for the migration advisory lock "
                        f"after {lock_timeout_ms / 1000:g}s (lock timeout; "
                        f"set {LOCK_TIMEOUT_ENV} to change the wait cap)"
                    ) from exc
                raise
            try:
                # The startup timeouts only bound lock acquisition.  Reset
                # them so long-running migration DDL is not aborted by them.
                await connection.execute(text("RESET statement_timeout"))
                await connection.execute(text("RESET lock_timeout"))
                # ``execute`` above auto-began a transaction; close it before
                # the migration's own transaction so DDL stays transactional
                # exactly as before.  The advisory lock is session-level and
                # survives this commit.
                await connection.commit()
                await connection.run_sync(
                    lambda conn: context.configure(
                        connection=conn, target_metadata=target_metadata
                    )
                )
                async with connection.begin():
                    await connection.run_sync(lambda conn: context.run_migrations())
            finally:
                # Session-level lock: release explicitly.  Closing the
                # connection would also release it, so never mask a migration
                # error if this best-effort unlock fails.
                try:
                    await connection.execute(text(_advisory_unlock_sql()))
                    await connection.commit()
                except Exception:
                    logger.warning(
                        "Failed to release alembic advisory lock", exc_info=True
                    )

    asyncio.run(run())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
