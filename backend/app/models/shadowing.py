"""Shadowing models (PRD §8.14).

``ShadowingClip``    one model voice per sentence, made once with TTS and reused
                     by everyone, so it is paid for once, not on every play.
``ShadowingAttempt`` one try by one learner at one sentence, with its score. The
                     learner's recording itself is never stored.
``ShadowingVideo``   a YouTube video cut into sentences by an admin (Phase 4).
``ShadowingSegment`` one sentence of a video: its text and where it starts and ends.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ShadowingClip(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shadowing_clips"

    # sha256 of model + voice + text. The same sentence in two topics shares one
    # clip, and an edited sentence gets a new clip instead of a stale recording.
    text_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    voice: Mapped[str] = mapped_column(String(40), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(40), nullable=False, default="audio/wav")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # In Postgres, not object storage: a few thousand short clips is a few hundred
    # MB at most, it needs no new service, and backup.sh already covers it. Move
    # to Cloudflare R2 if this table passes about 1 GB (PRD §8.14).
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class ShadowingVideo(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A video lesson. Only YouTube's id for the video is kept.

    The video and its sound are never downloaded (YouTube's terms forbid it):
    YouTube streams them in its own player, and an admin types the sentences and
    their times.
    """

    __tablename__ = "shadowing_videos"

    youtube_id: Mapped[str] = mapped_column(String(11), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str | None] = mapped_column(String(40), default=None)
    # Where the video comes from and why we may use it. Required to publish.
    source_note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    segments: Mapped[list["ShadowingSegment"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="ShadowingSegment.position",
        lazy="selectin",
    )


class ShadowingSegment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shadowing_segments"

    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shadowing_videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Order in the lesson: by start time, set on every save.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    translation: Mapped[str | None] = mapped_column(Text, default=None)

    video: Mapped[ShadowingVideo] = relationship(back_populates="segments")


class ShadowingAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shadowing_attempts"

    __table_args__ = (
        # The item lists read "my best score per sentence in this topic / video".
        Index("ix_shadowing_attempts_user_topic", "user_id", "topic_id", "created_at"),
        Index("ix_shadowing_attempts_user_video", "user_id", "video_id", "created_at"),
        # A try is at a topic sentence or a video sentence: never both, never neither.
        CheckConstraint(
            "(topic_id IS NULL) <> (video_id IS NULL)", name="ck_shadowing_attempts_one_source"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), default=None
    )
    video_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("shadowing_videos.id", ondelete="CASCADE"), default=None
    )
    # "<kind>-<uuid>" (see app/services/shadowing.py). Not a foreign key: it can
    # point at a question, an answer template, a doc item or a video segment.
    item_key: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_text: Mapped[str] = mapped_column(Text, nullable=False)
    heard_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Word match 0-100. NOT a pronunciation score (docs/10_AI_Design.md §10.3.11).
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    words_total: Mapped[int] = mapped_column(Integer, nullable=False)
    words_ok: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    reference_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    # browser = speech-to-text in the learner's browser (Web Speech or Whisper on
    # the device); server = POST /transcribe.
    engine: Mapped[str] = mapped_column(String(16), nullable=False)
