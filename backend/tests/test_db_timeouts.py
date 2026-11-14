"""T6.2: DB connection-level timeouts, worker pool settings, pool-exhaustion mapping.

DB-free: the engines are captured by monkeypatching ``create_async_engine`` so
the forwarded ``connect_args``/pool kwargs can be asserted without PostgreSQL.
The real server GUC values are covered by ``test_db_timeouts_pg.py``.

Defaults (decision Q9): API 30000/5000/60000 ms, worker 0/10000/300000 ms.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from galleryvault import observability
from galleryvault.app.dependencies import db_error
from galleryvault.config import Settings
from galleryvault.db import session as db_session

API_SERVER_SETTINGS = {
    "statement_timeout": "30000",
    "lock_timeout": "5000",
    "idle_in_transaction_session_timeout": "60000",
}
WORKER_SERVER_SETTINGS = {
    "statement_timeout": "0",
    "lock_timeout": "10000",
    "idle_in_transaction_session_timeout": "300000",
}


class _FakeEngine:
    def __init__(self) -> None:
        # ``create_database`` only probes ``sync_engine.pool``; None means
        # "no pool listeners", which is all these tests need.
        self.sync_engine = SimpleNamespace(pool=None)


def _capture_engines(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
    calls: list[tuple[str, dict]] = []

    def fake_create_async_engine(url: str, **kwargs: object):
        calls.append((url, dict(kwargs)))
        return _FakeEngine()

    monkeypatch.setattr(db_session, "create_async_engine", fake_create_async_engine)
    return calls


def _metric_value(name: str) -> float:
    for line in observability.render_metrics().splitlines():
        if line.startswith(name + " "):
            return float(line.rsplit(" ", 1)[1])
    return 0.0


def test_api_engine_sends_default_server_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_engines(monkeypatch)
    db_session.create_database(Settings())

    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs["connect_args"]["server_settings"] == API_SERVER_SETTINGS
    assert (
        kwargs["pool_size"],
        kwargs["max_overflow"],
        kwargs["pool_timeout"],
    ) == (30, 10, 30)


def test_worker_engine_sends_default_server_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_engines(monkeypatch)
    db_session.create_worker_database(Settings())

    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs["connect_args"]["server_settings"] == WORKER_SERVER_SETTINGS
    assert (
        kwargs["pool_size"],
        kwargs["max_overflow"],
        kwargs["pool_timeout"],
    ) == (5, 5, 30)


def test_timeouts_are_overridable_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_STATEMENT_TIMEOUT_MS", "1500")
    monkeypatch.setenv("DATABASE_LOCK_TIMEOUT_MS", "250")
    monkeypatch.setenv("DATABASE_IDLE_IN_TX_TIMEOUT_MS", "9000")
    monkeypatch.setenv("WORKER_DATABASE_STATEMENT_TIMEOUT_MS", "4500")
    monkeypatch.setenv("WORKER_DATABASE_LOCK_TIMEOUT_MS", "800")
    monkeypatch.setenv("WORKER_DATABASE_IDLE_IN_TX_TIMEOUT_MS", "12000")
    calls = _capture_engines(monkeypatch)

    db_session.create_database(Settings())
    db_session.create_worker_database(Settings())

    assert calls[0][1]["connect_args"]["server_settings"] == {
        "statement_timeout": "1500",
        "lock_timeout": "250",
        "idle_in_transaction_session_timeout": "9000",
    }
    assert calls[1][1]["connect_args"]["server_settings"] == {
        "statement_timeout": "4500",
        "lock_timeout": "800",
        "idle_in_transaction_session_timeout": "12000",
    }
    # The pool knobs are forwarded independently of the GUCs.
    assert calls[0][1]["pool_size"] == 30
    assert calls[1][1]["pool_size"] == 5


@pytest.mark.parametrize(
    "overrides",
    [
        {"worker_database_pool_size": 0},
        {"worker_database_max_overflow": -1},
        {"worker_database_pool_timeout": -1},
        {"database_statement_timeout_ms": -1},
        {"database_lock_timeout_ms": 86_400_001},
        {"worker_database_idle_in_tx_timeout_ms": -1},
    ],
)
def test_out_of_range_connection_settings_rejected(overrides: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Settings(**overrides)


def test_pool_timeout_maps_to_distinct_503(caplog: pytest.LogCaptureFixture) -> None:
    exc = PoolTimeoutError(
        "QueuePool limit of size 30 overflow 10 reached, connection timed out, timeout 30.00"
    )
    with caplog.at_level(logging.ERROR, logger="galleryvault.app.dependencies"):
        http = db_error(exc)

    assert http.status_code == 503
    assert http.detail == "Database pool exhausted"
    assert any(
        "pool exhausted" in record.getMessage().lower() for record in caplog.records
    )


def test_pool_timeout_increments_dedicated_counter() -> None:
    before = _metric_value("gv_db_pool_exhausted_total")
    db_error(PoolTimeoutError("connection timed out"))
    assert _metric_value("gv_db_pool_exhausted_total") == before + 1


def test_pool_exhaustion_is_not_generic_outage() -> None:
    pool = db_error(PoolTimeoutError("connection timed out"))
    generic = db_error(RuntimeError("connection refused"))
    assert pool.detail == "Database pool exhausted"
    assert generic.detail == "Database is unavailable"
    assert generic.status_code == 503


def test_integrity_error_keeps_409_mapping() -> None:
    http = db_error(IntegrityError("insert", {}, Exception("duplicate key")))
    assert http.status_code == 409
    assert http.detail == "Conflict"


def test_unrelated_timeout_error_is_not_pool_exhaustion() -> None:
    # asyncio timeouts are not SQLAlchemy pool timeouts and must keep the
    # generic outage mapping.
    http = db_error(TimeoutError("operation timed out"))
    assert http.detail == "Database is unavailable"
