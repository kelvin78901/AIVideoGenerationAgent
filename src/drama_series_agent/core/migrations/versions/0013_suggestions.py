"""M2 tables: suggestion (enrichment mirror) and suggestion_decision (SPEC 4.1).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "suggestion",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("para_idx", sa.Integer(), nullable=False),
        sa.Column("anchor_span_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_suggestion_series_id"), "suggestion", ["series_id"], unique=False)
    op.create_table(
        "suggestion_decision",
        sa.Column("suggestion_id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=True),
        sa.Column("rewrite_instruction", sa.String(), nullable=True),
        sa.Column("rewritten_by", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("suggestion_id"),
    )
    op.create_index(
        op.f("ix_suggestion_decision_series_id"),
        "suggestion_decision",
        ["series_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_suggestion_decision_series_id"), table_name="suggestion_decision")
    op.drop_table("suggestion_decision")
    op.drop_index(op.f("ix_suggestion_series_id"), table_name="suggestion")
    op.drop_table("suggestion")
