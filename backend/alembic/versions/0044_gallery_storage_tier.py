"""Add an explicit hot/cold storage tier to galleries.

Cold archiving used to be inferred from the ``storage_path`` prefix alone and
``storage_type`` described the on-disk format in both tiers.  ``storage_tier``
makes the location explicit; ``cold_at`` records when a gallery became cold.

The cold roots live in runtime settings (env + ``user_settings``), so the
migration only adds columns with the ``hot`` default: the idempotent
``reconcile_storage_tier`` startup pass backfills existing cold rows once the
archive roots are known.

Revision ID: 0044_gallery_storage_tier
Revises: 0043_download_ingest_state
Create Date: 2026-11-14
"""

import sqlalchemy as sa

from alembic import op

revision = "0044_gallery_storage_tier"
down_revision = "0043_download_ingest_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "galleries",
        sa.Column(
            "storage_tier",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'hot'"),
        ),
    )
    op.add_column(
        "galleries",
        sa.Column("cold_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_galleries_storage_tier",
        "galleries",
        "storage_tier IN ('hot', 'cold')",
    )
    op.create_index(
        "idx_galleries_storage_tier_cold",
        "galleries",
        ["id"],
        postgresql_where=sa.text("storage_tier = 'cold'"),
    )


def downgrade() -> None:
    op.drop_index("idx_galleries_storage_tier_cold", table_name="galleries")
    op.drop_constraint("ck_galleries_storage_tier", "galleries", type_="check")
    op.drop_column("galleries", "cold_at")
    op.drop_column("galleries", "storage_tier")
