"""add optional join password to rooms

Revision ID: 0011_room_password
Revises: 0010_sync_owner_and_phone
Create Date: 2026-07-27

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_room_password"
down_revision: str | None = "0010_sync_owner_and_phone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("rooms", "password_hash")
