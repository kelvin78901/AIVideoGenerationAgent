"""M2 tables: product, product_version, dependency, gate_decision.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "product",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("owner_type", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("slot", sa.String(), nullable=False),
        sa.Column("component_id", sa.String(), nullable=False),
        sa.Column("current_version_id", sa.String(), nullable=True),
        sa.Column("adopted_version_id", sa.String(), nullable=True),
        sa.Column("locked_hash", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("prompt_json", sa.JSON(), nullable=True),
        sa.Column("running_job_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_type", "owner_id", "slot"),
    )
    op.create_index(op.f("ix_product_series_id"), "product", ["series_id"], unique=False)
    op.create_table(
        "product_version",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("parent_version_id", sa.String(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("files_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("compiled", sa.String(), nullable=True),
        sa.Column("compiled_overridden", sa.Boolean(), nullable=False),
        sa.Column("model_key", sa.String(), nullable=True),
        sa.Column("where", sa.String(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("qa_json", sa.JSON(), nullable=True),
        sa.Column("qa_pass", sa.Boolean(), nullable=True),
        sa.Column("fallback_reason", sa.String(), nullable=True),
        sa.Column("stage", sa.String(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("workflow_id", sa.String(), nullable=True),
        sa.Column("workflow_sha256", sa.String(), nullable=True),
        sa.Column("comfy_env_hash", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "n"),
    )
    op.create_index(
        op.f("ix_product_version_product_id"), "product_version", ["product_id"], unique=False
    )
    op.create_table(
        "dependency",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("upstream_product_id", sa.String(), nullable=False),
        sa.Column("slice", sa.String(), nullable=False),
        sa.Column("upstream_hash", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["product_version.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dependency_version_id"), "dependency", ["version_id"], unique=False)
    op.create_index(op.f("ix_dependency_product_id"), "dependency", ["product_id"], unique=False)
    op.create_index(
        op.f("ix_dependency_upstream_product_id"),
        "dependency",
        ["upstream_product_id"],
        unique=False,
    )
    op.create_table(
        "gate_decision",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("gate", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("product_hashes_json", sa.JSON(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_gate_decision_series_id"), "gate_decision", ["series_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_gate_decision_series_id"), table_name="gate_decision")
    op.drop_table("gate_decision")
    op.drop_index(op.f("ix_dependency_upstream_product_id"), table_name="dependency")
    op.drop_index(op.f("ix_dependency_product_id"), table_name="dependency")
    op.drop_index(op.f("ix_dependency_version_id"), table_name="dependency")
    op.drop_table("dependency")
    op.drop_index(op.f("ix_product_version_product_id"), table_name="product_version")
    op.drop_table("product_version")
    op.drop_index(op.f("ix_product_series_id"), table_name="product")
    op.drop_table("product")
