"""record AI voice coach sessions

Creates ``ai_voice_sessions`` (PRD §8.12, docs/18_AI_Provider_Architecture.md
§18.13): one row per Gemini Live session started from Warm-up.

The browser streams audio straight to Gemini, so this table is the server's only
record of a session, and the source of the daily allowance. Time is measured on
the server clock and capped by ``max_seconds``, which is also baked into the
token's expiry — the browser never reports how long it talked.

Revision ID: 0021_ai_voice_sessions
Revises: 0020_user_role
Create Date: 2026-09-10

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_ai_voice_sessions"
down_revision: str | None = "0020_user_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_voice_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("max_seconds", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_seconds", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 8), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Every start reads "this user's sessions since midnight".
    op.create_index(
        "ix_ai_voice_sessions_user_created", "ai_voice_sessions", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_voice_sessions_user_created", table_name="ai_voice_sessions")
    op.drop_table("ai_voice_sessions")
