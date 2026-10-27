"""M5 step 7a: model_call.unpriced (a call to a model without a known price; its cost_usd is 0).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("model_call") as batch:
        batch.add_column(
            sa.Column("unpriced", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("model_call") as batch:
        batch.drop_column("unpriced")
