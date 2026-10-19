"""M2 table: bible_entity (story bible mirror, SPEC 4.1).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "bible_entity",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("aliases_json", sa.JSON(), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("paras_json", sa.JSON(), nullable=False),
        sa.Column("source_spans_json", sa.JSON(), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bible_entity_series_id"), "bible_entity", ["series_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_bible_entity_series_id"), table_name="bible_entity")
    op.drop_table("bible_entity")
