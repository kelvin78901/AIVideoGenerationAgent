"""M6 step 3: the take check's route (``takecheck``) merged into 自动质检 (``qa``): its saved
overrides move to ``qa``, replacing what ``qa`` had at the same scope.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DELETE FROM config_override
        WHERE component_id = 'qa'
          AND EXISTS (
            SELECT 1 FROM config_override AS t
            WHERE t.component_id = 'takecheck'
              AND t.scope = config_override.scope
              AND t.scope_id IS config_override.scope_id
          )
        """
    )
    op.execute("UPDATE config_override SET component_id = 'qa' WHERE component_id = 'takecheck'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE config_override SET component_id = 'takecheck' WHERE component_id = 'qa'")
