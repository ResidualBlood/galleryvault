"""Add indexes for gallery library sorting and filtering.

Additive only: indexes on galleries (rating, page_count, file_size) to support
fast multi-criteria sorting and range filtering on large local libraries.
"""

from alembic import op

revision = "0026_gallery_sort_indexes"
down_revision = "0025_gallery_metadata_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_galleries_rating",
        "galleries",
        ["rating"],
        unique=False,
    )
    op.create_index(
        "idx_galleries_page_count",
        "galleries",
        ["page_count"],
        unique=False,
    )
    op.create_index(
        "idx_galleries_file_size",
        "galleries",
        ["file_size"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_galleries_file_size", table_name="galleries")
    op.drop_index("idx_galleries_page_count", table_name="galleries")
    op.drop_index("idx_galleries_rating", table_name="galleries")
