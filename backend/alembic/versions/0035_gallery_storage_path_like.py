"""Index for gallery storage_path LIKE / startswith prefix search.

Creates btree index with text_pattern_ops on galleries.storage_path for PostgreSQL.
"""

from alembic import op

revision = "0035_gallery_storage_path_like"
down_revision = "0034_download_archive_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.create_index(
            "ix_gallery_storage_path_like",
            "galleries",
            ["storage_path"],
            postgresql_using="btree",
            postgresql_ops={"storage_path": "text_pattern_ops"},
        )
    else:
        op.create_index(
            "ix_gallery_storage_path_like",
            "galleries",
            ["storage_path"],
        )


def downgrade() -> None:
    op.drop_index("ix_gallery_storage_path_like", table_name="galleries")
