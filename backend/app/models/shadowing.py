"""Shadowing models (PRD §8.14).

``ShadowingClip``    one model voice per sentence, made once with TTS and reused
                     by everyone, so it is paid for once, not on every play.
``ShadowingAttempt`` one try by one learner at one sentence, with its score. The
                     learner's recording itself is never stored.
"""

import uuid

from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

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


class ShadowingAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shadowing_attempts"

    # The item list reads "my best score per sentence in this topic".
    __table_args__ = (
        Index("ix_shadowing_attempts_user_topic", "user_id", "topic_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    # "<kind>-<uuid>" (see app/services/shadowing.py). Not a foreign key: it can
    # point at a question, an answer template or a doc item.
    item_key: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_text: Mapped[str] = mapped_column(Text, nullable=False)
    heard_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Word match 0-100. NOT a pronunciation score (docs/10_AI_Design.md §10.3.11).
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    words_total: Mapped[int] = mapped_column(Integer, nullable=False)
    words_ok: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    reference_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    # browser = the Web Speech API in the learner's browser; server = POST /transcribe.
    engine: Mapped[str] = mapped_column(String(16), nullable=False)
