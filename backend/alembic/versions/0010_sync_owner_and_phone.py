"""sync migrations with models: add rooms.owner_id and users.phone

These two columns existed on the SQLAlchemy models but were never added by a
migration — in dev they were created by ``create_all`` (AUTO_CREATE_TABLES), which
masked the drift. In production (migrations only) their absence caused 500s on
``/rooms`` and ``/auth/login``. This reconciles the schema.

Revision ID: 0010_sync_owner_and_phone
Revises: 0009_user_is_admin
Create Date: 2026-07-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_sync_owner_and_phone"
down_revision: str | None = "0009_user_is_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # users.phone — optional, unique when set (matches User.phone).
    op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))
    op.create_unique_constraint("uq_users_phone", "users", ["phone"])

    # rooms.owner_id — nullable FK to users.id, SET NULL on delete (matches Room.owner_id).
    op.add_column("rooms", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_index("ix_rooms_owner_id", "rooms", ["owner_id"])
    op.create_foreign_key(
        "fk_rooms_owner_id_users", "rooms", "users", ["owner_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_rooms_owner_id_users", "rooms", type_="foreignkey")
    op.drop_index("ix_rooms_owner_id", table_name="rooms")
    op.drop_column("rooms", "owner_id")
    op.drop_constraint("uq_users_phone", "users", type_="unique")
    op.drop_column("users", "phone")
