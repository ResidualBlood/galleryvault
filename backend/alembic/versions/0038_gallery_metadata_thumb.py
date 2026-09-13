"""Restore gallery_metadata.thumb column.

Persists the thumbnail URL from gdata batch API so cover backfilling
can avoid extra network calls, falling back to HTML fetch_gallery_cover
only if the URL is expired or missing.
"""

import sqlalchemy as sa

from alembic import op

revision = "0038_gallery_metadata_thumb"
down_revision = "0037_download_archive_fallback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gallery_metadata", sa.Column("thumb", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("gallery_metadata", "thumb")
