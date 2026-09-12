"""shadowing: model-voice clips and scored attempts

Creates the two tables behind Shadowing (PRD §8.14):

* ``shadowing_clips`` — one TTS model voice per sentence, keyed by
  ``sha256(model, voice, text)``, so a sentence is paid for once and shared by
  every topic that uses it. Stored as ``bytea``: a few thousand short clips is a
  few hundred MB, needs no new service, and ``backup.sh`` already covers it.
* ``shadowing_attempts`` — one try by one learner at one sentence. Only the words
  heard and the word-match score are kept; the recording never leaves the browser.

Revision ID: 0022_shadowing
Revises: 0021_ai_voice_sessions
Create Date: 2026-09-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_shadowing"
down_revision: str | None = "0021_ai_voice_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "shadowing_clips",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("voice", sa.String(length=40), nullable=False),
        sa.Column("mime_type", sa.String(length=40), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("text_hash", name="uq_shadowing_clips_text_hash"),
    )

    op.create_table(
        "shadowing_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("item_key", sa.String(length=80), nullable=False),
        sa.Column("reference_text", sa.Text(), nullable=False),
        sa.Column("heard_text", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("words_total", sa.Integer(), nullable=False),
        sa.Column("words_ok", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("reference_ms", sa.Integer(), nullable=True),
        sa.Column("engine", sa.String(length=16), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # The item list reads "my best score per sentence in this topic".
    op.create_index(
        "ix_shadowing_attempts_user_topic",
        "shadowing_attempts",
        ["user_id", "topic_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_shadowing_attempts_user_topic", table_name="shadowing_attempts")
    op.drop_table("shadowing_attempts")
    op.drop_table("shadowing_clips")
