"""add username/password auth to users

Revision ID: 0008_user_auth
Revises: 0007_topic_sample_questions
Create Date: 2026-07-25

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_user_auth"
down_revision: str | None = "0007_topic_sample_questions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=40), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_users_username", "users", ["username"])


def downgrade() -> None:
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
