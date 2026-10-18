"""M1 tables: machine_profile, installed_item.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "machine_profile",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("machine", sa.String(), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "installed_item",
        sa.Column("profile_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("paths_json", sa.JSON(), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["machine_profile.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("profile_id", "item_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("installed_item")
    op.drop_table("machine_profile")
