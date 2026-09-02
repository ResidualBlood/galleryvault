"""Add index supporting the pending tag-sync discovery query."""

from alembic import op

revision = "0007_tags_synced_at_index"
down_revision = "0006_download_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_galleries_tags_synced_at",
        "galleries",
        ["tags_synced_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("idx_galleries_tags_synced_at", table_name="galleries", if_exists=True)
