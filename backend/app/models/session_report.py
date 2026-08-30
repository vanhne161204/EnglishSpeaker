"""SessionReport model — one IELTS band report (docs §10.3.7, §10.4).

Layer 2 of the Coach Report. Layer 1 (``sentence_feedback``) is a proofreader;
this is the teacher: *"what band am I, why, and what do I do this week?"*

One session produces one report **per learner** — each visible only to its own
``user_id``. Nothing another person said is ever written here (§10.3.0).
"""

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

#: Bands are exact half steps. Numeric, never Float — 6.5 stored as a float
#: comes back as 6.4999998 in something a student may screenshot.
_BAND = Numeric(2, 1)


class SessionReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "session_reports"

    __table_args__ = (
        # Every band-history query. Progress over time is the retention hook.
        Index("ix_report_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), index=True, default=None
    )

    # conversation | ielts_part1 | ielts_part2 | ielts_part3. Decides whether the
    # UI may call this a "band" or must say "estimated band" (§10.3.12).
    mode: Mapped[str] = mapped_column(
        String(20), default="conversation", server_default="conversation", nullable=False
    )

    band_fluency: Mapped[float] = mapped_column(_BAND, nullable=False)
    band_lexical: Mapped[float] = mapped_column(_BAND, nullable=False)
    band_grammar: Mapped[float] = mapped_column(_BAND, nullable=False)
    # Null until real pronunciation scoring exists. No model accepts audio, so a
    # number here today would be invented (§10.3.11).
    band_pronunciation: Mapped[float | None] = mapped_column(_BAND, default=None)
    band_overall: Mapped[float] = mapped_column(_BAND, nullable=False)

    pronunciation_assessed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    # True while `band_overall` averages only three criteria. The UI must label
    # the number whenever this is set.
    overall_is_estimate: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )

    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    next_band: Mapped[float] = mapped_column(_BAND, nullable=False)

    # Per-criterion evidence and justification. Evidence holds the learner's own
    # words ONLY — `strip_foreign_quotes` runs before anything is written here.
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    blockers: Mapped[list] = mapped_column(JSON, default=list)
    drills: Mapped[list] = mapped_column(JSON, default=list)
    # The computed SpeechMetrics, kept so a report can be re-read later without
    # recomputing from segments that may since have been deleted.
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)

    model: Mapped[str] = mapped_column(String(48), nullable=False, default="")
    # How many evidence quotes `strip_foreign_quotes` had to remove. Non-zero
    # means the prompt's role separation is slipping — surfaced to admin review.
    quotes_removed: Mapped[int] = mapped_column(
        Numeric(4, 0), default=0, server_default="0", nullable=False
    )
