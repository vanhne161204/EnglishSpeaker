"""shadowing videos: YouTube video lessons cut into sentences

Adds Shadowing Phase 4 (PRD §8.14):

* ``shadowing_videos`` — a YouTube video id, a title, a level, and the source and
  permission note an admin must fill in before publishing. The video itself is
  never downloaded or stored.
* ``shadowing_segments`` — the video's sentences, each with its start and end.
* ``shadowing_attempts`` — a try can now be at a video sentence: ``topic_id``
  becomes nullable, ``video_id`` is added, and a check makes sure exactly one of
  the two is set.

Revision ID: 0023_shadowing_videos
Revises: 0022_shadowing
Create Date: 2026-09-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_shadowing_videos"
down_revision: str | None = "0022_shadowing"
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
        "shadowing_videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("youtube_id", sa.String(length=11), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=True),
        sa.Column("source_note", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadowing_videos_youtube_id", "shadowing_videos", ["youtube_id"])

    op.create_table(
        "shadowing_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("translation", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["video_id"], ["shadowing_videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadowing_segments_video_id", "shadowing_segments", ["video_id"])

    op.alter_column("shadowing_attempts", "topic_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("shadowing_attempts", sa.Column("video_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_shadowing_attempts_video_id",
        "shadowing_attempts",
        "shadowing_videos",
        ["video_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_shadowing_attempts_one_source",
        "shadowing_attempts",
        "(topic_id IS NULL) <> (video_id IS NULL)",
    )
    op.create_index(
        "ix_shadowing_attempts_user_video",
        "shadowing_attempts",
        ["user_id", "video_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_shadowing_attempts_user_video", table_name="shadowing_attempts")
    op.drop_constraint("ck_shadowing_attempts_one_source", "shadowing_attempts", type_="check")
    op.drop_constraint("fk_shadowing_attempts_video_id", "shadowing_attempts", type_="foreignkey")
    # Tries at video sentences have no topic; they cannot survive NOT NULL.
    op.execute("DELETE FROM shadowing_attempts WHERE video_id IS NOT NULL")
    op.drop_column("shadowing_attempts", "video_id")
    op.alter_column("shadowing_attempts", "topic_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_index("ix_shadowing_segments_video_id", table_name="shadowing_segments")
    op.drop_table("shadowing_segments")
    op.drop_index("ix_shadowing_videos_youtube_id", table_name="shadowing_videos")
    op.drop_table("shadowing_videos")
