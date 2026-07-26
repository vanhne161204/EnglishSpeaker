"""rooms and sentence_notes

Revision ID: 0002_rooms_and_notes
Revises: 0001_initial
Create Date: 2026-06-22

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_rooms_and_notes"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=True),
        sa.Column("level", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("capacity", sa.Integer(), server_default="4", nullable=False),
        sa.Column("participant_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rooms_mode", "rooms", ["mode"])

    op.create_table(
        "sentence_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("improved_text", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=20), server_default="self", nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("sentence_notes")
    op.drop_index("ix_rooms_mode", table_name="rooms")
    op.drop_table("rooms")
