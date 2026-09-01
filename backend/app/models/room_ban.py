"""RoomBan model — who may not rejoin which room (PRD §8.3, docs/11_Security.md Step 4).

Replaces the in-memory ban registry this project shipped with. Three things were
wrong with a Python dict:

* **It died with the process.** Every deploy — and this project deploys on every
  push to main — silently un-banned everyone.
* **It never expired.** A host who mis-clicked banned somebody from that room
  forever, and no endpoint existed to undo it.
* **It was per-instance.** A second API container would not have seen the ban at
  all.

``expires_at`` is nullable and NULL means permanent. That is deliberate: a
temporary ban is the normal case, but an admin acting on an abuse report needs to
be able to make one stick.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class RoomBan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "room_bans"

    __table_args__ = (
        # One live ban per (room, user). Re-banning updates the row instead of
        # stacking duplicates that would each have to be lifted separately.
        UniqueConstraint("room_id", "user_id", name="uq_room_bans_room_user"),
        # The join path reads this on every attempt, so it has to be an index.
        Index("ix_room_bans_room_user", "room_id", "user_id"),
        # The admin queue lists newest first.
        Index("ix_room_bans_created_at", "created_at"),
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Who issued it: the room owner, or an admin acting on a report. Nullable so
    # deleting that account does not delete the ban it issued.
    banned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    reason: Mapped[str | None] = mapped_column(String(200), default=None)

    # NULL = permanent. Anything in the past is expired and no longer enforced.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
