"""Coach Report layer 1 — per-sentence feedback (docs/10_AI_Design.md §10.3).

What the AI found in ONE sentence the learner spoke: a grammar fix, a stronger
word, a paraphrase, and the natural version. The learner's permanent record of
their own mistakes, and the evidence layer 2's grammar band will lean on.

Relationship to the tables around it (§10.4):

    transcript_segments  ->  sentence_feedback  ->  [learner taps Save]  ->  sentence_notes
       (what I said)          (what AI found)                                (my wordbook)

``sentence_feedback`` is generated and disposable — re-runnable at any time.
``sentence_notes`` is what the learner chose to keep. Do not conflate them.
"""

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SentenceFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sentence_feedback"

    __table_args__ = (
        # "My mistakes, newest first" — the learner-facing history view.
        Index("ix_feedback_user_created", "user_id", "created_at"),
        # The dedupe cache. Learners repeat the same broken phrase constantly, so
        # this lookup runs before every API call and must not be a scan.
        Index("ix_feedback_hash", "text_hash"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Null for warm-up practice, which has no room.
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), index=True, default=None
    )
    # The transcript line this grades. SET NULL rather than CASCADE: deleting a
    # transcript should not silently erase the learning that came out of it.
    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transcript_segments.id", ondelete="SET NULL"), default=None
    )

    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    # sha256 of the normalised text — the cache key that avoids paying twice for
    # the same sentence.
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    corrected: Mapped[str | None] = mapped_column(Text, default=None)
    natural: Mapped[str] = mapped_column(Text, nullable=False, default="")
    paraphrase: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # JSON, not child tables: these are rendered, never queried *into*. Three
    # extra joins would buy nothing. The one aggregate we do want — "which
    # mistake do I repeat most" — is a GROUP BY on the JSON key (§10.5).
    errors: Mapped[list] = mapped_column(JSON, default=list)
    vocab: Mapped[list] = mapped_column(JSON, default=list)

    cefr: Mapped[str | None] = mapped_column(String(4), default=None)
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Which model produced this. Kept so a later "why was this feedback poor?"
    # can be answered, and so an A/B between models is possible after the fact.
    model: Mapped[str] = mapped_column(String(48), nullable=False, default="")


class FeedbackJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks one background assessment so the UI can show real progress.

    Without it, "Analysing your session…" is a spinner that lies: the learner
    cannot tell a slow job from a dead one.
    """

    __tablename__ = "feedback_jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), index=True, default=None
    )
    # queued | running | done | failed
    status: Mapped[str] = mapped_column(
        String(20), default="queued", server_default="queued", nullable=False
    )
    total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    done: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, default=None)
