"""Keep one current history row per gallery and persist favorite checks."""

import sqlalchemy as sa

from alembic import op

revision = "0005_fav_logs_hist_unique"
down_revision = "0004_history_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM reading_history old
        USING reading_history newer
        WHERE old.gallery_id = newer.gallery_id AND old.id < newer.id
    """)
    op.create_unique_constraint("uq_reading_history_gallery", "reading_history", ["gallery_id"])
    op.create_table(
        "favorites_check_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("favcat", sa.Integer(), nullable=False),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("discovered_gids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index(
        "idx_favorites_check_logs_category", "favorites_check_logs", ["favcat", "checked_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_favorites_check_logs_category", table_name="favorites_check_logs")
    op.drop_table("favorites_check_logs")
    op.drop_constraint("uq_reading_history_gallery", "reading_history", type_="unique")
