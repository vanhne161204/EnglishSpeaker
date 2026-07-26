"""add is_admin flag to users

Revision ID: 0009_user_is_admin
Revises: 0008_user_auth
Create Date: 2026-07-25

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_user_is_admin"
down_revision: str | None = "0008_user_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
