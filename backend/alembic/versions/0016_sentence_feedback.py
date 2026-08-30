"""store what the coach found in each spoken sentence

Creates ``sentence_feedback`` and ``feedback_jobs`` — Coach Report layer 1
(docs/10_AI_Design.md §10.3, §10.4).

``errors`` and ``vocab`` are JSON rather than child tables on purpose: they are
rendered, never queried *into*, so three extra joins would buy nothing.

``text_hash`` is the dedupe cache key. Learners repeat the same broken phrase
constantly, and a sentence already graded must never be paid for twice — hence
its own index, hit before every API call.

``segment_id`` is SET NULL, not CASCADE: deleting a transcript should not
silently erase the learning that came out of it.

Revision ID: 0016_sentence_feedback
Revises: 0015_transcript_segments
Create Date: 2026-08-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_sentence_feedback"
down_revision: str | None = "0015_transcript_segments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sentence_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("segment_id", sa.Uuid(), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("corrected", sa.Text(), nullable=True),
        sa.Column("natural", sa.Text(), nullable=False, server_default=""),
        sa.Column("paraphrase", sa.Text(), nullable=False, server_default=""),
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("vocab", sa.JSON(), nullable=True),
        sa.Column("cefr", sa.String(length=4), nullable=True),
        sa.Column("score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("model", sa.String(length=48), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["segment_id"], ["transcript_segments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sentence_feedback_user_id", "sentence_feedback", ["user_id"])
    op.create_index("ix_sentence_feedback_room_id", "sentence_feedback", ["room_id"])
    op.create_index("ix_feedback_user_created", "sentence_feedback", ["user_id", "created_at"])
    op.create_index("ix_feedback_hash", "sentence_feedback", ["text_hash"])

    op.create_table(
        "feedback_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("done", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_jobs_user_id", "feedback_jobs", ["user_id"])
    op.create_index("ix_feedback_jobs_room_id", "feedback_jobs", ["room_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_jobs_room_id", table_name="feedback_jobs")
    op.drop_index("ix_feedback_jobs_user_id", table_name="feedback_jobs")
    op.drop_table("feedback_jobs")
    op.drop_index("ix_feedback_hash", table_name="sentence_feedback")
    op.drop_index("ix_feedback_user_created", table_name="sentence_feedback")
    op.drop_index("ix_sentence_feedback_room_id", table_name="sentence_feedback")
    op.drop_index("ix_sentence_feedback_user_id", table_name="sentence_feedback")
    op.drop_table("sentence_feedback")
