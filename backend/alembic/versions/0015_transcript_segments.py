"""store what people actually said in a room

Creates ``transcript_segments`` (PRD §8.9) — one row per finalised sentence of
speech. This is the written record of a conversation, and the input to the whole
Coach Report feature in docs/10_AI_Design.md §10.3.

Only FINALISED segments are stored. Interim speech-to-text results are broadcast
over the WebSocket so the room watches words appear, then dropped; persisting
them would multiply writes roughly 15x for text that is replaced a second later.

``stt_confidence`` ships now even though nothing reads it until the pronunciation
work (§10.3.11): once a session ends, the engine's confidence score is gone and
cannot be backfilled.

Revision ID: 0015_transcript_segments
Revises: 0014_ai_usage
Create Date: 2026-08-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_transcript_segments"
down_revision: str | None = "0014_ai_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("speaker_name", sa.String(length=80), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("source", sa.String(length=20), server_default="browser", nullable=False),
        sa.Column("seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column("spoken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stt_confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcript_segments_room_id", "transcript_segments", ["room_id"])
    op.create_index("ix_transcript_segments_user_id", "transcript_segments", ["user_id"])
    op.create_index("ix_transcript_segments_spoken_at", "transcript_segments", ["spoken_at"])
    # Composite indexes for the two queries that actually run: "the last N lines
    # of this room" (every client, on every join) and "everything I have said".
    op.create_index("ix_transcript_room_spoken", "transcript_segments", ["room_id", "spoken_at"])
    op.create_index("ix_transcript_user_spoken", "transcript_segments", ["user_id", "spoken_at"])


def downgrade() -> None:
    op.drop_index("ix_transcript_user_spoken", table_name="transcript_segments")
    op.drop_index("ix_transcript_room_spoken", table_name="transcript_segments")
    op.drop_index("ix_transcript_segments_spoken_at", table_name="transcript_segments")
    op.drop_index("ix_transcript_segments_user_id", table_name="transcript_segments")
    op.drop_index("ix_transcript_segments_room_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")
