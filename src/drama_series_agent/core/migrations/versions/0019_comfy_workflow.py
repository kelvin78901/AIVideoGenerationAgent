"""M5: comfy_workflow (the workflow library) and model_call's workflow columns.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "comfy_workflow",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("model_key", sa.String(), nullable=False),
        sa.Column("name_json", sa.JSON(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("dir", sa.String(), nullable=False),
        sa.Column("origin", sa.String(), nullable=True),
        sa.Column("file_sha256", sa.String(), nullable=False),
        sa.Column("bindings_json", sa.JSON(), nullable=False),
        sa.Column("deps_json", sa.JSON(), nullable=False),
        sa.Column("caps_json", sa.JSON(), nullable=False),
        sa.Column("check_json", sa.JSON(), nullable=True),
        sa.Column("trial_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_comfy_workflow_slug"), "comfy_workflow", ["slug"], unique=True)
    with op.batch_alter_table("model_call") as batch:
        batch.add_column(sa.Column("workflow_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("workflow_sha256", sa.String(), nullable=True))
        batch.add_column(sa.Column("comfy_env_hash", sa.String(), nullable=True))
        batch.add_column(sa.Column("select_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("model_call") as batch:
        batch.drop_column("select_json")
        batch.drop_column("comfy_env_hash")
        batch.drop_column("workflow_sha256")
        batch.drop_column("workflow_id")
    op.drop_index(op.f("ix_comfy_workflow_slug"), table_name="comfy_workflow")
    op.drop_table("comfy_workflow")
