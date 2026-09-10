"""AiVoiceSession — one AI voice coach session (PRD §8.12, docs §18.13).

The browser talks to Gemini directly, so this row is the server's only record of
a session, and the only thing the daily allowance is counted from. Time is
measured on the server clock (``created_at`` to ``ended_at``), never reported by
the browser: a client that skips the "end" call cannot make a session free, and
one that lies about its length cannot make it cheaper.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AiVoiceSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_voice_sessions"

    # Every start reads "this user's sessions since midnight".
    __table_args__ = (Index("ix_ai_voice_sessions_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), default=None
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)

    # The hard limit baked into the token. Held in full against the allowance
    # while the session is open, so two tabs cannot each spend the same minutes.
    max_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Null while open. Set by the "end" call, or by a later request that finds
    # the session past its expiry (the learner closed the tab without ending it).
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    used_seconds: Mapped[int | None] = mapped_column(Integer, default=None)

    # Estimated, not invoiced — see app/ai/pricing.py `gemini_live_cost`.
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 8), default=0, server_default="0", nullable=False
    )
