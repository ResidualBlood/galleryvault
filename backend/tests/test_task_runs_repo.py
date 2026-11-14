"""T7.4: ``TaskRun`` model + ``TaskRunRepository`` (DB-free).

Host runs have no PostgreSQL, so these tests assert the generated SQL/params
(the same approach as ``test_audit_gallery_repo_contract.py``) and the model
shape.  The real table/backfill/constraints are exercised by the PG integration
test in ``test_alembic_0046.py`` (container-only).
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql

from galleryvault.db.models import TaskRun
from galleryvault.db.repositories.task_runs import (
    MAX_NAME_LENGTH,
    MAX_PAYLOAD_BYTES,
    TaskRunRepository,
    truncate_payload,
)

_PG = postgresql.dialect()


def _sql(stmt: object) -> str:
    return str(stmt.compile(dialect=_PG, compile_kwargs={"literal_binds": True})).replace(
        "\n", " "
    )


def _sql_plain(stmt: object) -> str:
    return str(stmt.compile(dialect=_PG)).replace("\n", " ")


def _params(stmt: object) -> dict[str, object]:
    return dict(stmt.compile(dialect=_PG).params)


class _Result:
    def __init__(self, rowcount: int = 1) -> None:
        self.rowcount = rowcount


class _Scalars:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)


class _Session:
    def __init__(
        self,
        *,
        rowcount: int = 1,
        scalar_value: object | None = None,
        rows: list[object] | None = None,
    ) -> None:
        self.rowcount = rowcount
        self.scalar_value = scalar_value
        self.rows = list(rows or [])
        self.statements: list[object] = []
        self.scalar_stmt: object | None = None
        self.scalars_stmt: object | None = None

    async def execute(self, stmt: object) -> _Result:
        self.statements.append(stmt)
        return _Result(self.rowcount)

    async def scalar(self, stmt: object) -> object | None:
        self.scalar_stmt = stmt
        return self.scalar_value

    async def scalars(self, stmt: object) -> _Scalars:
        self.scalars_stmt = stmt
        return _Scalars(self.rows)


# --------------------------------------------------------------------------- #
# payload bound
# --------------------------------------------------------------------------- #


def test_small_payload_is_kept_verbatim() -> None:
    payload = {"corrupt_ids": [1, 2], "categories": {"doujinshi": 3}}

    assert truncate_payload(payload) == payload
    assert truncate_payload(None) == {}


def test_payload_is_truncated_with_marker_above_256kb() -> None:
    marker_overhead = len(json.dumps({"data": ""}, separators=(",", ":"), sort_keys=True).encode())
    payload = {"data": "a" * (MAX_PAYLOAD_BYTES - marker_overhead)}
    assert truncate_payload(payload) == payload  # exactly at the limit

    oversized = {"data": "a" * (MAX_PAYLOAD_BYTES - marker_overhead + 1)}
    truncated = truncate_payload(oversized)

    assert truncated["truncated"] is True
    assert truncated["original_bytes"] > MAX_PAYLOAD_BYTES
    assert set(truncated) == {"truncated", "original_bytes"}
    assert "data" not in truncated


def test_payload_must_be_a_mapping() -> None:
    with pytest.raises(TypeError):
        truncate_payload(["not", "a", "mapping"])  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# start / heartbeat / finish
# --------------------------------------------------------------------------- #


async def test_start_interrupts_stale_running_row_then_inserts() -> None:
    session = _Session()
    repo = TaskRunRepository(session)

    run_id = await repo.start("scan", payload={"source": "manual"})

    assert len(run_id) == 36
    stale, insert = session.statements
    stale_sql = _sql(stale)
    assert "UPDATE task_runs" in stale_sql
    assert "task_runs.name = 'scan'" in stale_sql
    assert "task_runs.status = 'running'" in stale_sql
    assert _params(stale)["status"] == "interrupted"

    insert_sql = _sql_plain(insert)
    assert "INSERT INTO task_runs" in insert_sql
    insert_params = _params(insert)
    assert insert_params["run_id"] == run_id
    assert insert_params["status"] == "running"
    assert _params(insert)["cancellable"] is False
    assert _params(insert)["payload"] == {"source": "manual"}


async def test_start_truncates_oversized_payload() -> None:
    session = _Session()
    await TaskRunRepository(session).start("scan", payload={"ids": ["x" * 1000] * 400})

    _, insert = session.statements
    payload = _params(insert)["payload"]
    assert payload["truncated"] is True
    assert payload["original_bytes"] > MAX_PAYLOAD_BYTES


async def test_start_validates_name_and_run_id_length() -> None:
    repo = TaskRunRepository(_Session())

    with pytest.raises(ValueError):
        await repo.start("   ")
    with pytest.raises(ValueError):
        await repo.start("x" * (MAX_NAME_LENGTH + 1))
    with pytest.raises(ValueError):
        await repo.start("scan", run_id="r" * 37)


async def test_heartbeat_updates_only_the_running_row() -> None:
    session = _Session(rowcount=1)
    repo = TaskRunRepository(session)

    matched = await repo.heartbeat("scan", 3, 9, stage="pages", payload={"current": 3})

    assert matched is True
    stmt = session.statements[0]
    sql = _sql_plain(stmt)
    assert "UPDATE task_runs" in sql
    assert "task_runs.name = " in sql
    assert "task_runs.status = " in sql
    params = _params(stmt)
    assert (params["done"], params["total"], params["stage"]) == (3, 9, "pages")
    assert params["payload"] == {"current": 3}
    assert params["heartbeat_at"] is not None


async def test_heartbeat_without_match_returns_false_and_keeps_stage() -> None:
    session = _Session(rowcount=0)
    repo = TaskRunRepository(session)

    assert await repo.heartbeat("scan", 1, 2) is False
    assert "stage" not in _params(session.statements[0])


async def test_heartbeat_can_target_explicit_run_id() -> None:
    session = _Session()
    await TaskRunRepository(session).heartbeat("scan", run_id="abc")

    assert "task_runs.run_id = 'abc'" in _sql(session.statements[0])


async def test_finish_sets_terminal_status_and_reason() -> None:
    session = _Session(rowcount=1)
    repo = TaskRunRepository(session)

    assert await repo.finish("scan", "failed", "boom", done=4, total=9) is True

    stmt = session.statements[0]
    sql = _sql(stmt)
    assert "task_runs.status = 'running'" in sql  # only closes a live row
    params = _params(stmt)
    assert params["status"] == "failed"
    assert params["reason"] == "boom"
    assert params["last_error"] == "boom"
    assert params["completed_at"] is not None
    assert (params["done"], params["total"]) == (4, 9)


async def test_finish_success_does_not_set_last_error() -> None:
    session = _Session()
    await TaskRunRepository(session).finish("scan", "success")

    params = _params(session.statements[0])
    assert params["reason"] is None
    assert "last_error" not in params


async def test_finish_rejects_non_terminal_status() -> None:
    repo = TaskRunRepository(_Session())

    with pytest.raises(ValueError):
        await repo.finish("scan", "running")
    with pytest.raises(ValueError):
        await repo.finish("scan", "unknown")


# --------------------------------------------------------------------------- #
# reads / reconciliation / prune
# --------------------------------------------------------------------------- #


async def test_latest_returns_newest_row_for_name() -> None:
    row = TaskRun(id=7, name="scan", run_id="r", status="running")
    session = _Session(scalar_value=row)

    assert await TaskRunRepository(session).latest("scan") is row
    sql = _sql(session.scalar_stmt)
    assert "task_runs.name = 'scan'" in sql
    assert "ORDER BY task_runs.started_at DESC, task_runs.id DESC" in sql
    assert "LIMIT 1" in sql


async def test_history_orders_by_completion_and_can_filter_name() -> None:
    rows = [TaskRun(id=1, name="scan", run_id="r")]
    session = _Session(rows=rows)

    assert await TaskRunRepository(session).history(5) == rows
    sql = _sql(session.scalars_stmt)
    assert "coalesce(task_runs.completed_at, task_runs.started_at) DESC" in sql
    assert "LIMIT 5" in sql

    session = _Session(rows=rows)
    await TaskRunRepository(session).history(5, name="thumbs")
    assert "task_runs.name = 'thumbs'" in _sql(session.scalars_stmt)


async def test_history_limit_zero_skips_query() -> None:
    session = _Session()

    assert await TaskRunRepository(session).history(0) == []
    assert session.scalars_stmt is None


async def test_mark_interrupted_updates_all_running_rows() -> None:
    session = _Session(rowcount=2)

    assert await TaskRunRepository(session).mark_interrupted() == 2
    stmt = session.statements[0]
    assert "task_runs.status = 'running'" in _sql(stmt)
    params = _params(stmt)
    assert params["status"] == "interrupted"
    assert params["reason"] == "interrupted by restart"


async def test_prune_keeps_newest_n_finished_runs_per_name() -> None:
    session = _Session(rowcount=4)

    assert await TaskRunRepository(session).prune(3) == 4
    sql = _sql(session.statements[0])
    assert "DELETE FROM task_runs" in sql
    assert "row_number() over (partition by task_runs.name" in sql.lower()
    assert "task_runs.status != 'running'" in sql
    assert "> 3" in sql


async def test_prune_rejects_non_positive_keep() -> None:
    with pytest.raises(ValueError):
        await TaskRunRepository(_Session()).prune(0)


# --------------------------------------------------------------------------- #
# model shape / exports
# --------------------------------------------------------------------------- #


def test_task_run_table_shape_matches_plan() -> None:
    table = TaskRun.__table__

    assert [column.name for column in table.columns] == [
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
    assert table.c.name.type.length == 48
    assert table.c.run_id.type.length == 36
    assert table.c.status.type.length == 16
    assert table.c.name.nullable is False
    assert table.c.status.nullable is False
    assert table.c.cancellable.nullable is False
    assert table.c.done.nullable is False
    assert table.c.total.nullable is False
    assert table.c.payload.nullable is False
    assert table.c.started_at.nullable is False
    assert table.c.completed_at.nullable is True

    checks = [
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    ]
    assert any("status IN" in text and "interrupted" in text for text in checks)
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_task_runs_name_run_id"
        and [column.name for column in constraint.columns] == ["name", "run_id"]
        for constraint in table.constraints
    )

    indexes = {index.name: index for index in table.indexes}
    running = indexes["idx_task_runs_running_name"]
    assert running.unique is True
    assert "status = 'running'" in str(running.dialect_options["postgresql"]["where"])
    completed = indexes["idx_task_runs_name_completed"]
    assert [str(expression) for expression in completed.expressions] == [
        "task_runs.name",
        "completed_at DESC",
    ]


def test_repository_is_exported_from_package() -> None:
    from galleryvault.db import repositories

    assert repositories.TaskRunRepository is TaskRunRepository
    assert "TaskRunRepository" in repositories.__all__
