"""M5 step 7a: provider model lists (provider_account.models_json / enabled_json) and
model_setting (a user's model id or price for one model).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("provider_account") as batch:
        batch.add_column(sa.Column("models_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("enabled_json", sa.JSON(), nullable=True))
    op.create_table(
        "model_setting",
        sa.Column("model_key", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("price_json", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("model_key"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("model_setting")
    with op.batch_alter_table("provider_account") as batch:
        batch.drop_column("enabled_json")
        batch.drop_column("models_json")
