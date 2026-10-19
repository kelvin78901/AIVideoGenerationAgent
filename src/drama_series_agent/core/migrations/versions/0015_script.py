"""M2 tables: scene and script_line (剧本化 mirror, SPEC 4.1).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "scene",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("episode_id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=True),
        sa.Column("time_of_day", sa.String(), nullable=True),
        sa.Column("paras_json", sa.JSON(), nullable=False),
        sa.Column("source_spans_json", sa.JSON(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scene_episode_id"), "scene", ["episode_id"], unique=False)
    op.create_index(op.f("ix_scene_series_id"), "scene", ["series_id"], unique=False)
    op.create_table(
        "script_line",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("episode_id", sa.String(), nullable=False),
        sa.Column("scene_id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=True),
        sa.Column("character_name", sa.String(), nullable=True),
        sa.Column("tone", sa.String(), nullable=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("mood", sa.String(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("overlay_shot", sa.String(), nullable=True),
        sa.Column("paras_json", sa.JSON(), nullable=False),
        sa.Column("source_spans_json", sa.JSON(), nullable=False),
        sa.Column("ai_added", sa.Boolean(), nullable=False),
        sa.Column("cliffhanger", sa.Boolean(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_script_line_episode_id"), "script_line", ["episode_id"], unique=False)
    op.create_index(op.f("ix_script_line_scene_id"), "script_line", ["scene_id"], unique=False)
    op.create_index(op.f("ix_script_line_series_id"), "script_line", ["series_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_script_line_series_id"), table_name="script_line")
    op.drop_index(op.f("ix_script_line_scene_id"), table_name="script_line")
    op.drop_index(op.f("ix_script_line_episode_id"), table_name="script_line")
    op.drop_table("script_line")
    op.drop_index(op.f("ix_scene_series_id"), table_name="scene")
    op.drop_index(op.f("ix_scene_episode_id"), table_name="scene")
    op.drop_table("scene")
