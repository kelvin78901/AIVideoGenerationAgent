"""M5.5 step 2: shot.contract_json (镜头契约), asset.manual (an asset the user made by hand).

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("shot") as batch:
        batch.add_column(sa.Column("contract_json", sa.JSON(), nullable=True))
    with op.batch_alter_table("asset") as batch:
        batch.add_column(
            sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("asset") as batch:
        batch.drop_column("manual")
    with op.batch_alter_table("shot") as batch:
        batch.drop_column("contract_json")
