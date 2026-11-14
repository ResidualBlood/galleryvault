"""Create ``task_runs`` and import the legacy ``app_config.task_history``.

T7.4 of PLAN-backend-hardening: task state lived only in memory plus one JSONB
document (``app_config['task_history']``).  This migration adds the durable
ledger the persistence layer (T7.5) reads, and copies the already-persisted
history so the Logs page does not lose records across the switch.

Backfill mapping:

* each ``history[]`` entry becomes one finished row; ``task`` -> ``name``,
  ``run_id`` is a deterministic uuid derived from its position so re-running
  the statement cannot duplicate rows (``ON CONFLICT DO NOTHING``);
* ``status`` is kept when it is a known terminal value, otherwise ``failed``
  (the old writer only emitted success/failed/cancelled);
* ISO timestamps are parsed only when they look like ISO-8601; unparseable
  values become NULL instead of aborting the migration;
* ``payload`` stays empty — the legacy record had no structured detail.

``downgrade()`` drops the table; ``app_config`` is left untouched.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0046_task_runs"
down_revision = "0045_duplicate_groups"
branch_labels = None
depends_on = None

_ISO_TS = "'^[0-9]{4}-[0-9]{2}-[0-9]{2}T'"
_INT = "'^-?[0-9]+$'"


def upgrade() -> None:
    op.create_table(
        "task_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column(
            "cancellable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("done", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'failed', 'cancelled', 'interrupted')",
            name="ck_task_runs_status",
        ),
        sa.UniqueConstraint("name", "run_id", name="uq_task_runs_name_run_id"),
    )
    op.create_index(
        "idx_task_runs_running_name",
        "task_runs",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "idx_task_runs_name_completed",
        "task_runs",
        ["name", sa.text("completed_at DESC")],
    )

    status = (
        "CASE WHEN item.value->>'status' IN "
        "('success', 'failed', 'cancelled', 'interrupted') "
        "THEN item.value->>'status' ELSE 'failed' END"
    )
    completed_at = (
        f"CASE WHEN item.value->>'completed_at' ~ {_ISO_TS} "
        "THEN (item.value->>'completed_at')::timestamptz END"
    )
    started_at = (
        f"CASE WHEN item.value->>'started_at' ~ {_ISO_TS} "
        "THEN (item.value->>'started_at')::timestamptz END"
    )
    done = (
        f"CASE WHEN item.value->>'done' ~ {_INT} "
        "THEN (item.value->>'done')::integer ELSE 0 END"
    )
    total = (
        f"CASE WHEN item.value->>'total' ~ {_INT} "
        "THEN (item.value->>'total')::integer ELSE 0 END"
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO task_runs (
                name, run_id, status, stage, cancellable, done, total,
                last_error, reason, payload, started_at, completed_at,
                heartbeat_at, created_at, updated_at
            )
            SELECT
                left(item.value->>'task', 48),
                md5(
                    concat_ws(
                        '|',
                        item.ord::text,
                        item.value->>'task',
                        COALESCE(item.value->>'completed_at', '')
                    )
                )::uuid::text,
                parsed.status,
                NULL,
                false,
                parsed.done,
                parsed.total,
                CASE
                    WHEN parsed.status = 'failed'
                        THEN NULLIF(item.value->>'reason', '')
                END,
                NULLIF(item.value->>'reason', ''),
                '{{}}'::jsonb,
                COALESCE(parsed.started_at, parsed.completed_at, now()),
                parsed.completed_at,
                parsed.completed_at,
                COALESCE(parsed.completed_at, parsed.started_at, now()),
                COALESCE(parsed.completed_at, parsed.started_at, now())
            FROM app_config AS config
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(config.value->'history') = 'array'
                        THEN config.value->'history'
                    ELSE '[]'::jsonb
                END
            ) WITH ORDINALITY AS item(value, ord)
            CROSS JOIN LATERAL (
                SELECT
                    {status} AS status,
                    {done} AS done,
                    {total} AS total,
                    {started_at} AS started_at,
                    {completed_at} AS completed_at
            ) AS parsed
            WHERE config.key = 'task_history'
              AND item.value->>'task' IS NOT NULL
            ON CONFLICT (name, run_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("idx_task_runs_name_completed", table_name="task_runs")
    op.drop_index("idx_task_runs_running_name", table_name="task_runs")
    op.drop_table("task_runs")
