"""M4 table: shot (分镜规划 mirror).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "shot",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("episode_id", sa.String(), nullable=False),
        sa.Column("scene_id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("shot_type", sa.String(), nullable=False),
        sa.Column("framing", sa.String(), nullable=False),
        sa.Column("camera_move", sa.String(), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("manual_s", sa.Float(), nullable=True),
        sa.Column("intent", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("sound", sa.String(), nullable=True),
        sa.Column("line_ids_json", sa.JSON(), nullable=False),
        sa.Column("asset_ids_json", sa.JSON(), nullable=False),
        sa.Column("tail_from", sa.String(), nullable=True),
        sa.Column("tail_note", sa.String(), nullable=True),
        sa.Column("blocking_json", sa.JSON(), nullable=False),
        sa.Column("audio_mode", sa.String(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("control_json", sa.JSON(), nullable=True),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shot_episode_id"), "shot", ["episode_id"], unique=False)
    op.create_index(op.f("ix_shot_scene_id"), "shot", ["scene_id"], unique=False)
    op.create_index(op.f("ix_shot_series_id"), "shot", ["series_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_shot_series_id"), table_name="shot")
    op.drop_index(op.f("ix_shot_scene_id"), table_name="shot")
    op.drop_index(op.f("ix_shot_episode_id"), table_name="shot")
    op.drop_table("shot")
