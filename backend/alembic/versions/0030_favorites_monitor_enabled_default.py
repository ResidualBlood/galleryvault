"""Change favorites_monitor.enabled server_default to false.

New favorites monitor rows default to disabled (opt-in). Existing rows are
unmodified.
"""

import sqlalchemy as sa

from alembic import op

revision = "0030_favmon_enabled_default"
down_revision = "0029_local_lists_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "favorites_monitor",
        "enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("false"),
    )


def downgrade() -> None:
    op.alter_column(
        "favorites_monitor",
        "enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("true"),
    )
