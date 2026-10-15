"""M1 tables: series, output_spec.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "series",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("ui_lang", sa.String(), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "output_spec",
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("aspect", sa.String(), nullable=False),
        sa.Column("delivery", sa.String(), nullable=False),
        sa.Column("fps", sa.Integer(), nullable=False),
        sa.Column("episode_len", sa.String(), nullable=False),
        sa.Column("subtitles", sa.String(), nullable=False),
        sa.Column("audio_json", sa.JSON(), nullable=False),
        sa.Column("codec", sa.String(), nullable=False),
        sa.Column("ai_mark", sa.Boolean(), nullable=False),
        sa.Column("derive", sa.String(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("series_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("output_spec")
    op.drop_table("series")
