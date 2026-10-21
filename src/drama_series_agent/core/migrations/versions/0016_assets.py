"""M3 tables: asset and asset_use (素材分析 mirror); product.pick_json and product.retired.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "asset",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("bible_id", sa.String(), nullable=True),
        sa.Column("seed_json", sa.JSON(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_asset_series_id"), "asset", ["series_id"], unique=False)
    op.create_table(
        "asset_use",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("episode_id", sa.String(), nullable=False),
        sa.Column("scene_id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("line_ids_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_asset_use_asset_id"), "asset_use", ["asset_id"], unique=False)
    op.create_index(op.f("ix_asset_use_episode_id"), "asset_use", ["episode_id"], unique=False)
    op.create_index(op.f("ix_asset_use_series_id"), "asset_use", ["series_id"], unique=False)
    with op.batch_alter_table("product") as batch:
        batch.add_column(sa.Column("pick_json", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("product") as batch:
        batch.drop_column("retired")
        batch.drop_column("pick_json")
    op.drop_index(op.f("ix_asset_use_series_id"), table_name="asset_use")
    op.drop_index(op.f("ix_asset_use_episode_id"), table_name="asset_use")
    op.drop_index(op.f("ix_asset_use_asset_id"), table_name="asset_use")
    op.drop_table("asset_use")
    op.drop_index(op.f("ix_asset_series_id"), table_name="asset")
    op.drop_table("asset")
