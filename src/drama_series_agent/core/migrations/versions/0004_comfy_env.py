"""M1 table: comfy_env.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "comfy_env",
        sa.Column("hash", sa.String(), nullable=False),
        sa.Column("comfyui_version", sa.String(), nullable=True),
        sa.Column("comfyui_commit", sa.String(), nullable=True),
        sa.Column("python", sa.String(), nullable=True),
        sa.Column("torch", sa.String(), nullable=True),
        sa.Column("node_packs_json", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("hash"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("comfy_env")
