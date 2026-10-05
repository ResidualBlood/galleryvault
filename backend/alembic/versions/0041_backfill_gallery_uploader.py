"""Backfill gallery uploader from metadata and sync uploader tags.

Revision ID: 0041_backfill_gallery_uploader
Revises: 0040_uploader_tags_backfill
Create Date: 2026-10-05
"""

from alembic import op

revision = "0041_backfill_gallery_uploader"
down_revision = "0040_uploader_tags_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = [
        """
        UPDATE galleries g
        SET uploader = TRIM(gm.uploader)
        FROM gallery_metadata gm
        WHERE g.gid = gm.gid
          AND (g.uploader IS NULL OR TRIM(g.uploader) = '')
          AND gm.uploader IS NOT NULL
          AND TRIM(gm.uploader) <> '';
        """,
        """
        INSERT INTO tags (namespace, name)
        SELECT DISTINCT 'uploader', TRIM(g.uploader)
        FROM galleries g
        WHERE g.uploader IS NOT NULL AND TRIM(g.uploader) <> ''
        ON CONFLICT (namespace, name) DO NOTHING;
        """,
        """
        INSERT INTO gallery_tags (gallery_id, tag_id)
        SELECT g.id, t.id
        FROM galleries g
        JOIN tags t ON t.namespace = 'uploader' AND t.name = TRIM(g.uploader)
        WHERE g.uploader IS NOT NULL AND TRIM(g.uploader) <> ''
        ON CONFLICT DO NOTHING;
        """,
    ]
    for stmt in statements:
        op.execute(stmt)


def downgrade() -> None:
    pass
