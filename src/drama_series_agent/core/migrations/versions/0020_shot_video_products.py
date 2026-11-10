"""M5: every shot has a video product (slot ``video``, component ``vid``).

New plans get theirs when they are materialized (``shots/service.py:materialize``); this adds
them to the shots already there.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-26
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade data."""
    conn = op.get_bind()
    shots = conn.execute(
        sa.text(
            "SELECT s.id, s.series_id, s.retired FROM shot s WHERE NOT EXISTS ("
            " SELECT 1 FROM product p WHERE p.owner_type = 'shot' AND p.owner_id = s.id"
            " AND p.slot = 'video')"
        )
    ).all()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")  # as SQLAlchemy stores it
    for shot_id, series_id, retired in shots:
        conn.execute(
            sa.text(
                "INSERT INTO product (id, series_id, owner_type, owner_id, slot, component_id,"
                " status, retired, created_at, updated_at) VALUES (:id, :series, 'shot', :shot,"
                " 'video', 'vid', 'empty', :retired, :now, :now)"
            ),
            {
                "id": uuid.uuid4().hex,
                "series": series_id,
                "shot": shot_id,
                "retired": bool(retired),
                "now": now,
            },
        )


def downgrade() -> None:
    """Downgrade data."""
    op.execute(
        "DELETE FROM product_version WHERE product_id IN ("
        " SELECT id FROM product WHERE owner_type = 'shot' AND slot = 'video')"
    )
    op.execute("DELETE FROM product WHERE owner_type = 'shot' AND slot = 'video'")
