"""M2: job.episode_id and job.confirmed_usd (budget checks, SPEC 7.6).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("job") as batch:
        batch.add_column(sa.Column("episode_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("confirmed_usd", sa.Float(), nullable=True))
        batch.create_index(batch.f("ix_job_episode_id"), ["episode_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("job") as batch:
        batch.drop_index(batch.f("ix_job_episode_id"))
        batch.drop_column("confirmed_usd")
        batch.drop_column("episode_id")
