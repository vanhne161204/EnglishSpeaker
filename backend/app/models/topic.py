"""Topic model — conversation subjects managed by admins (PRD §8.1)."""

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Topic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "topics"

    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    level: Mapped[str | None] = mapped_column(String(40), default=None)
    status: Mapped[str] = mapped_column(String(20), default="published", server_default="published")
    # Admin-authored sample questions used by Warm-up (PRD §8.1). JSON list of
    # strings so it works on both SQLite (dev default) and Postgres.
    sample_questions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
