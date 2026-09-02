"""Trigram GIN indexes for substring title search.

``list_page`` searches with ``title ILIKE '%q%'`` (a leading-wildcard
substring), which the existing FTS GIN index cannot accelerate.  A ``pg_trgm``
GIN index on each title column turns that into an index-assisted bitmap OR at
large library sizes (100k+ galleries).
"""

import sqlalchemy as sa  # noqa: F401  (import order guard)

from alembic import op

revision = "0015_galleries_title_trgm"
down_revision = "0014_duplicate_ignores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_galleries_title_trgm "
        "ON galleries USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_galleries_title_jpn_trgm "
        "ON galleries USING gin (title_jpn gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_galleries_title_jpn_trgm")
    op.execute("DROP INDEX IF EXISTS idx_galleries_title_trgm")
