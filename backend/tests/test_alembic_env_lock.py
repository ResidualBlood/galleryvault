"""T6.4: alembic online migrations serialise on a PostgreSQL advisory lock.

Every replica runs ``alembic upgrade head`` from ``entrypoint.sh``; without a
lock two replicas can race on the same DDL.  ``run_migrations_online`` must
therefore acquire a session-level advisory lock on its migration connection
*before* configuring/running migrations, bound the wait with a configurable
timeout (default 120s), and release it afterwards.  Offline mode is unchanged.

These tests are DB-free: they load ``alembic/env.py`` under a fake
``alembic.context`` and a fake connection that records the SQL it executes.
The real PostgreSQL behaviour (contention, lock timeout) is covered by the
container acceptance commands.
"""

import importlib.util
import uuid
from pathlib import Path

import alembic.context as alembic_context
import pytest

ENV_PATH = Path(__file__).resolve().parent.parent / "alembic" / "env.py"


class _SyncContextManager:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _AsyncContextManager:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc_info):
        return False


class FakeConnection:
    """Records ``execute`` statements; ``run_sync`` calls the callback inline."""

    def __init__(self, events):
        self.events = events

    async def execute(self, statement, parameters=None):
        self.events.append(("execute", str(statement), parameters))
        return FakeResult()

    async def run_sync(self, fn):
        return fn(self)

    async def commit(self):
        self.events.append(("commit",))

    def begin(self):
        return _AsyncContextManager(self)


class FakeResult:
    def scalar(self):
        return True


class _TimeoutConnection(FakeConnection):
    """Fails the first execute with the PostgreSQL statement-timeout error."""

    async def execute(self, statement, parameters=None):
        self.events.append(("execute", str(statement), parameters))
        raise RuntimeError("canceling statement due to statement timeout")


class FakeConnectable:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return _AsyncContextManager(self.connection)


class FakeConfig:
    config_file_name = None
    config_ini_section = "alembic"

    def set_main_option(self, *args, **kwargs):
        return None

    def get_main_option(self, name):
        return "postgresql+asyncpg://user:pass@localhost/galleryvault"

    def get_section(self, *args, **kwargs):
        return {}


def _load_env(monkeypatch, *, offline=True, keep_bootstrap=False):
    """Import env.py with a fake alembic context.

    ``offline=True`` keeps the module-level bootstrap from creating a real
    engine; online behaviour is exercised by calling ``run_migrations_online``
    explicitly with a fake engine factory.  The bootstrap's own context calls
    are dropped unless the caller is testing offline mode (``keep_bootstrap``).
    """
    events = []
    configure_calls = []

    def fake_configure(**kwargs):
        configure_calls.append(kwargs)
        events.append(("configure", kwargs))

    def fake_run_migrations():
        events.append(("run_migrations",))

    monkeypatch.setattr(alembic_context, "config", FakeConfig(), raising=False)
    monkeypatch.setattr(alembic_context, "is_offline_mode", lambda: offline)
    monkeypatch.setattr(alembic_context, "configure", fake_configure)
    monkeypatch.setattr(alembic_context, "run_migrations", fake_run_migrations)
    monkeypatch.setattr(
        alembic_context, "begin_transaction", lambda: _SyncContextManager()
    )

    spec = importlib.util.spec_from_file_location(
        f"alembic_env_{uuid.uuid4().hex}", ENV_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not keep_bootstrap:
        events.clear()
        configure_calls.clear()
    return module, events, configure_calls


def _executed(events):
    return [event for event in events if event[0] == "execute"]


def test_online_migration_takes_advisory_lock_first(monkeypatch):
    module, events, _ = _load_env(monkeypatch)
    connection = FakeConnection(events)
    module.async_engine_from_config = lambda *args, **kwargs: FakeConnectable(
        connection
    )

    module.run_migrations_online()

    executed = _executed(events)
    assert executed, "run_migrations_online executed no SQL"
    first_sql = executed[0][1]
    assert "pg_advisory_lock" in first_sql
    assert str(module.ADVISORY_LOCK_KEY) in first_sql
    last_sql = executed[-1][1]
    assert "pg_advisory_unlock" in last_sql
    assert str(module.ADVISORY_LOCK_KEY) in last_sql

    lock_index = events.index(executed[0])
    migration_index = events.index(("run_migrations",))
    unlock_index = events.index(executed[-1])
    assert lock_index < migration_index < unlock_index


def test_lock_timeout_does_not_leak_into_migration_ddl(monkeypatch):
    module, events, _ = _load_env(monkeypatch)
    connection = FakeConnection(events)
    module.async_engine_from_config = lambda *args, **kwargs: FakeConnectable(
        connection
    )

    module.run_migrations_online()

    executed = _executed(events)
    # The acquisition timeout is set as a connection startup parameter; it is
    # reset once the lock is held so lengthy migration DDL is not bounded by it.
    reset = [event for event in executed if "lock_timeout" in event[1].lower()]
    assert reset, "lock_timeout was not reset after acquiring the lock"
    reset_index = events.index(reset[0])
    migration_index = events.index(("run_migrations",))
    assert reset_index < migration_index


def test_unlock_runs_when_migration_fails(monkeypatch):
    module, events, _ = _load_env(monkeypatch)

    def boom():
        raise RuntimeError("migration failed")

    # Patch after import so the module-level offline bootstrap is unaffected.
    monkeypatch.setattr(alembic_context, "run_migrations", boom)
    connection = FakeConnection(events)
    module.async_engine_from_config = lambda *args, **kwargs: FakeConnectable(
        connection
    )

    with pytest.raises(RuntimeError, match="migration failed"):
        module.run_migrations_online()

    executed = _executed(events)
    assert "pg_advisory_unlock" in executed[-1][1]


def test_offline_mode_does_not_touch_advisory_lock(monkeypatch):
    module, events, configure_calls = _load_env(
        monkeypatch, offline=True, keep_bootstrap=True
    )

    assert module is not None
    assert configure_calls, "offline configure was not called"
    assert "url" in configure_calls[0]
    assert ("run_migrations",) in events
    assert not _executed(events)


def test_lock_timeout_defaults_to_120_seconds(monkeypatch):
    module, events, _ = _load_env(monkeypatch)
    monkeypatch.delenv(module.LOCK_TIMEOUT_ENV, raising=False)
    captured = {}

    def factory(*args, **kwargs):
        captured.update(kwargs)
        return FakeConnectable(FakeConnection(events))

    module.async_engine_from_config = factory
    module.run_migrations_online()

    assert captured["connect_args"]["server_settings"]["lock_timeout"] == "120000"
    assert captured["connect_args"]["server_settings"]["statement_timeout"] == "120000"


def test_lock_timeout_is_configurable(monkeypatch):
    module, events, _ = _load_env(monkeypatch)
    monkeypatch.setenv(module.LOCK_TIMEOUT_ENV, "3")
    captured = {}

    def factory(*args, **kwargs):
        captured.update(kwargs)
        return FakeConnectable(FakeConnection(events))

    module.async_engine_from_config = factory
    module.run_migrations_online()

    assert captured["connect_args"]["server_settings"]["lock_timeout"] == "3000"
    assert captured["connect_args"]["server_settings"]["statement_timeout"] == "3000"


def test_lock_wait_timeout_is_reported_as_lock_timeout(monkeypatch):
    module, events, _ = _load_env(monkeypatch)
    monkeypatch.setenv(module.LOCK_TIMEOUT_ENV, "3")
    module.async_engine_from_config = lambda *args, **kwargs: FakeConnectable(
        _TimeoutConnection(events)
    )

    with pytest.raises(RuntimeError, match="lock timeout"):
        module.run_migrations_online()


def test_invalid_lock_timeout_is_rejected(monkeypatch):
    module, events, _ = _load_env(monkeypatch)
    monkeypatch.setenv(module.LOCK_TIMEOUT_ENV, "soon")
    module.async_engine_from_config = lambda *args, **kwargs: FakeConnectable(
        FakeConnection(events)
    )

    with pytest.raises(RuntimeError, match="lock timeout"):
        module.run_migrations_online()
