"""Category model — groups topics into themes (PRD §8.1).

A category is a shelf: "Daily Life", "Work", "Travel". Topics point at one (or at
none, in which case the UI files them under "Other"), so a long topic list stays
easy to scan.
"""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    icon_url: Mapped[str | None] = mapped_column(String(500), default=None)
    # Admin-controlled display order; ties are broken by name in the repository.
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
