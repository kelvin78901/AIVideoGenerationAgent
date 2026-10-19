"""M2 tables: novel_source and chapter (novel import, SPEC 4.1).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "novel_source",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("original_sha256", sa.String(), nullable=False),
        sa.Column("encoding", sa.String(), nullable=False),
        sa.Column("split_by", sa.String(), nullable=False),
        sa.Column("chars", sa.Integer(), nullable=False),
        sa.Column("rights_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_novel_source_series_id"), "novel_source", ["series_id"], unique=False)
    op.create_table(
        "chapter",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=False),
        sa.Column("para_start", sa.Integer(), nullable=False),
        sa.Column("paras_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["novel_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "idx"),
    )
    op.create_index(op.f("ix_chapter_source_id"), "chapter", ["source_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_chapter_source_id"), table_name="chapter")
    op.drop_table("chapter")
    op.drop_index(op.f("ix_novel_source_series_id"), table_name="novel_source")
    op.drop_table("novel_source")
