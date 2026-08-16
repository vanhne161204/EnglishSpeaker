"""Topic model — conversation subjects managed by admins (PRD §8.1)."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Topic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "topics"

    # Optional grouping. ``SET NULL`` so deleting a category never deletes topics —
    # they just fall back to the UI's "Other" group.
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True, default=None
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    level: Mapped[str | None] = mapped_column(String(40), default=None)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[str] = mapped_column(String(20), default="published", server_default="published")
    # Admin-controlled display order; ties are broken by title in the repository.
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
