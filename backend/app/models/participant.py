"""RoomParticipant model — who is currently in a room (PRD §8.3).

A participant row links a user to a room. ``display_name`` is a snapshot taken at
join time so incognito rooms can show a temporary name without exposing the real
profile. A row with ``left_at IS NULL`` is an active participant.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class RoomParticipant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "room_participants"

    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Name shown to others in this room (a temporary alias in incognito mode).
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
