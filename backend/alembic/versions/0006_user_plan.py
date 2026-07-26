"""add subscription plan to users

Revision ID: 0006_user_plan
Revises: 0005_documents
Create Date: 2026-06-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_user_plan"
down_revision: str | None = "0005_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("plan", sa.String(length=20), server_default="free", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "plan")
