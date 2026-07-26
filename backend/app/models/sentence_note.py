"""SentenceNote model — useful sentences a user saves (PRD §8.7).

Note: no ``user_id`` yet — that arrives with the auth slice. For the first demo
notes are global.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SentenceNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sentence_notes"

    original_text: Mapped[str | None] = mapped_column(Text, default=None)
    improved_text: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str] = mapped_column(String(20), default="self", server_default="self")
    topic: Mapped[str | None] = mapped_column(String(120), default=None)
