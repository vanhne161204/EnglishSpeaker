"""record what every AI call costs

Creates the ``ai_usage`` ledger (docs/18_AI_Provider_Architecture.md §18.8) — one
row per LLM call, with tokens, cost, latency and whether a fallback answered.

This is the input to pricing and to the free-tier caps. Vendor dashboards show an
org total; they cannot attribute spend to a user, a tier, or a feature. Spend that
was never recorded cannot be recovered later, so this ships before the AI features
that will generate it, not after.

``cost_usd`` is NUMERIC(12, 8), not a float: a single rescue call costs about
$0.000011, so three decimal places would round every call to zero.

Revision ID: 0014_ai_usage
Revises: 0013_note_translation_pair
Create Date: 2026-08-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_ai_usage"
down_revision: str | None = "0013_note_translation_pair"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("task", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("model", sa.String(length=48), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cached_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 8), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("degraded", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("ok", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_user_id", "ai_usage", ["user_id"])
    op.create_index("ix_ai_usage_room_id", "ai_usage", ["room_id"])
    op.create_index("ix_ai_usage_task", "ai_usage", ["task"])
    op.create_index("ix_ai_usage_model", "ai_usage", ["model"])
    # The budget guard runs this on EVERY call: "spend since <date>", and
    # "calls by this user since <date>". Without the composite index those are
    # full scans on the fastest-growing table in the schema.
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])
    op.create_index(
        "ix_ai_usage_user_task_created", "ai_usage", ["user_id", "task", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_user_task_created", table_name="ai_usage")
    op.drop_index("ix_ai_usage_created_at", table_name="ai_usage")
    op.drop_index("ix_ai_usage_model", table_name="ai_usage")
    op.drop_index("ix_ai_usage_task", table_name="ai_usage")
    op.drop_index("ix_ai_usage_room_id", table_name="ai_usage")
    op.drop_index("ix_ai_usage_user_id", table_name="ai_usage")
    op.drop_table("ai_usage")
