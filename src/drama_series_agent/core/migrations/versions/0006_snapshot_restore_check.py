"""M1 step 8c: a rollback is checked after ComfyUI restarts (comfy_snapshot.restore_*).

Rollbacks requested before this revision were never checked: they keep their request time as
``restore_requested_at`` with state ``unchecked``, and ``restored_at`` (now: when a check found
ComfyUI back at the snapshot) is cleared.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("comfy_snapshot") as batch:
        batch.add_column(
            sa.Column("restore_requested_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("restore_from_hash", sa.String(), nullable=True))
        batch.add_column(sa.Column("restore_state", sa.String(), nullable=True))
        batch.add_column(sa.Column("restore_diff_json", sa.JSON(), nullable=True))
    op.execute(
        "UPDATE comfy_snapshot SET restore_requested_at = restored_at, "
        "restore_state = 'unchecked', restored_at = NULL WHERE restored_at IS NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE comfy_snapshot SET restored_at = restore_requested_at "
        "WHERE restore_requested_at IS NOT NULL"
    )
    with op.batch_alter_table("comfy_snapshot") as batch:
        batch.drop_column("restore_diff_json")
        batch.drop_column("restore_state")
        batch.drop_column("restore_from_hash")
        batch.drop_column("restore_requested_at")
