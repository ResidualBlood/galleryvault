"""Add trash (soft delete) columns for recycle bin.

Additive only: galleries.trashed + galleries.trashed_at + indexes.
Separate from expunged (scan missing) for two distinct recycle lists.
"""

import sqlalchemy as sa

from alembic import op

revision = "0027_gallery_trash"
down_revision = "0026_gallery_sort_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("galleries", sa.Column("trashed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("galleries", sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_galleries_trashed", "galleries", ["trashed"], unique=False)
    op.create_index("idx_galleries_expunged", "galleries", ["expunged"], unique=False)
    # Backfill: ensure existing rows have trashed=false
    op.execute(sa.text("UPDATE galleries SET trashed = false WHERE trashed IS NULL"))
    # Drop default after backfill (keep column default false for future inserts)
    # server_default remains false, no need to drop


def downgrade() -> None:
    op.drop_index("idx_galleries_expunged", table_name="galleries")
    op.drop_index("idx_galleries_trashed", table_name="galleries")
    op.drop_column("galleries", "trashed_at")
    op.drop_column("galleries", "trashed")
