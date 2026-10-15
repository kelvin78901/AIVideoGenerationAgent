"""M0 core tables: job, model_call, config_override, provider_account, custom_model, event.

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "config_override",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("component_id", sa.String(), nullable=True),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "scope_id", "component_id"),
    )
    op.create_table(
        "custom_model",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("price_in", sa.Float(), nullable=True),
        sa.Column("price_out", sa.Float(), nullable=True),
        sa.Column("caps_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "model_id"),
    )
    op.create_table(
        "event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=True),
        sa.Column("product_id", sa.String(), nullable=True),
        sa.Column("component_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("queue", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("depends_on_json", sa.JSON(), nullable=False),
        sa.Column("est_cost_usd", sa.Float(), nullable=True),
        sa.Column("fallback_from_job_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_job_product_id"), ["product_id"], unique=False)
        batch_op.create_index("ix_job_queue_state", ["queue", "state", "priority"], unique=False)
        batch_op.create_index(batch_op.f("ix_job_series_id"), ["series_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_job_state"), ["state"], unique=False)

    op.create_table(
        "model_call",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=True),
        sa.Column("episode_id", sa.String(), nullable=True),
        sa.Column("scene_id", sa.String(), nullable=True),
        sa.Column("shot_id", sa.String(), nullable=True),
        sa.Column("component_id", sa.String(), nullable=True),
        sa.Column("product_id", sa.String(), nullable=True),
        sa.Column("version_id", sa.String(), nullable=True),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("provider_id", sa.String(), nullable=True),
        sa.Column("model_key", sa.String(), nullable=False),
        sa.Column("where", sa.String(), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), nullable=False),
        sa.Column("fallback_reason", sa.String(), nullable=True),
        sa.Column("is_switch", sa.Boolean(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("images", sa.Integer(), nullable=True),
        sa.Column("output_seconds", sa.Float(), nullable=True),
        sa.Column("chars", sa.Integer(), nullable=True),
        sa.Column("input_seconds", sa.Float(), nullable=True),
        sa.Column("unit_prices_json", sa.JSON(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("billed", sa.Boolean(), nullable=False),
        sa.Column("vram_peak_mb", sa.Integer(), nullable=True),
        sa.Column("gpu_util_avg", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("qa_scores_json", sa.JSON(), nullable=True),
        sa.Column("qa_pass", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("model_call", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_model_call_component_id"), ["component_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_model_call_episode_id"), ["episode_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_model_call_job_id"), ["job_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_model_call_series_id"), ["series_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_model_call_started_at"), ["started_at"], unique=False)

    op.create_table(
        "provider_account",
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("has_key", sa.Boolean(), nullable=False),
        sa.Column("key_ref", sa.String(), nullable=True),
        sa.Column("base_url_override", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("provider_account")
    with op.batch_alter_table("model_call", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_model_call_started_at"))
        batch_op.drop_index(batch_op.f("ix_model_call_series_id"))
        batch_op.drop_index(batch_op.f("ix_model_call_job_id"))
        batch_op.drop_index(batch_op.f("ix_model_call_episode_id"))
        batch_op.drop_index(batch_op.f("ix_model_call_component_id"))

    op.drop_table("model_call")
    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_job_state"))
        batch_op.drop_index(batch_op.f("ix_job_series_id"))
        batch_op.drop_index("ix_job_queue_state")
        batch_op.drop_index(batch_op.f("ix_job_product_id"))

    op.drop_table("job")
    op.drop_table("event")
    op.drop_table("custom_model")
    op.drop_table("config_override")
