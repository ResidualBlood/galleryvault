"""Backfill uploader tags.

Revision ID: 0040_uploader_tags_backfill
Revises: 0039_audit_constraints
Create Date: 2026-10-05
"""

from alembic import op

revision = "0040_uploader_tags_backfill"
down_revision = "0039_audit_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = [
        """
        INSERT INTO tags (namespace, name)
        SELECT DISTINCT 'uploader', TRIM(uploader)
        FROM galleries
        WHERE uploader IS NOT NULL AND TRIM(uploader) <> ''
        ON CONFLICT (namespace, name) DO NOTHING
        """,
        """
        INSERT INTO gallery_tags (gallery_id, tag_id)
        SELECT g.id, t.id
        FROM galleries g
        JOIN tags t ON t.namespace = 'uploader' AND t.name = TRIM(g.uploader)
        WHERE g.uploader IS NOT NULL AND TRIM(g.uploader) <> ''
        ON CONFLICT DO NOTHING
        """,
    ]
    for stmt in statements:
        op.execute(stmt)


def downgrade() -> None:
    pass
