"""Room model — a place users join to have a conversation (PRD §8.3)."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Room(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rooms"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # The user who created the room and can moderate it (PRD §8.3 owner controls).
    # Null for system-seeded rooms, which have no owner.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True, default=None
    )
    # Stored as a short string; validated against ConversationMode at the API layer.
    mode: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    # group | one_on_one — a 1-on-1 is just a room with capacity 2 (validated
    # against RoomKind at the API layer). One model serves both.
    kind: Mapped[str] = mapped_column(
        String(20), index=True, nullable=False, default="group", server_default="group"
    )
    topic: Mapped[str | None] = mapped_column(String(120), default=None)
    level: Mapped[str | None] = mapped_column(String(40), default=None)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    capacity: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    participant_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Optional join password (PRD §8.3). NULL = public room. Stored as a bcrypt
    # hash — the raw password is never persisted or returned.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)

    @property
    def has_password(self) -> bool:
        """Whether joining this room requires a password (never exposes the hash)."""
        return self.password_hash is not None
