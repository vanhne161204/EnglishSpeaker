"""add kind to rooms (unify group and 1-on-1)

Revision ID: 0003_room_kind
Revises: 0002_rooms_and_notes
Create Date: 2026-06-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_room_kind"
down_revision: str | None = "0002_rooms_and_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rooms",
        sa.Column("kind", sa.String(length=20), server_default="group", nullable=False),
    )
    op.create_index("ix_rooms_kind", "rooms", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_rooms_kind", table_name="rooms")
    op.drop_column("rooms", "kind")
