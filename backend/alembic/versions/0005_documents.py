"""documents (admin learning content per topic)

Revision ID: 0005_documents
Revises: 0004_users_membership_messages
Create Date: 2026-06-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_documents"
down_revision: str | None = "0004_users_membership_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind", sa.String(length=30), server_default="explanation", nullable=False
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_topic_id", "documents", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_topic_id", table_name="documents")
    op.drop_table("documents")
