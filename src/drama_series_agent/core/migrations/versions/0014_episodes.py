"""M2 tables: episode and beat (分集规划 mirror, SPEC 4.1).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "episode",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("hook", sa.String(), nullable=True),
        sa.Column("cliffhanger", sa.String(), nullable=True),
        sa.Column("target_seconds", sa.Integer(), nullable=True),
        sa.Column("scene_count", sa.Integer(), nullable=True),
        sa.Column("budget_usd", sa.Float(), nullable=True),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_episode_series_id"), "episode", ["series_id"], unique=False)
    op.create_table(
        "beat",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("episode_id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("emotion", sa.Float(), nullable=False),
        sa.Column("paras_json", sa.JSON(), nullable=False),
        sa.Column("source_spans_json", sa.JSON(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_beat_episode_id"), "beat", ["episode_id"], unique=False)
    op.create_index(op.f("ix_beat_series_id"), "beat", ["series_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_beat_series_id"), table_name="beat")
    op.drop_index(op.f("ix_beat_episode_id"), table_name="beat")
    op.drop_table("beat")
    op.drop_index(op.f("ix_episode_series_id"), table_name="episode")
    op.drop_table("episode")
