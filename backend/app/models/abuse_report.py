"""AbuseReport model — one learner reporting another (docs/11_Security.md §11.9).

The product puts strangers in a voice call together. Until now there was no way
to report what happened in one, which is not a missing feature so much as a
missing obligation.

The reported **text is snapshotted**, not referenced. A message can be deleted
and a transcript segment can be purged by retention, but the report has to stay
readable long enough for someone to act on it. A report whose evidence has
vanished is worse than no report.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ReportStatus(StrEnum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


class AbuseReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "abuse_reports"

    __table_args__ = (
        # The queue is "open reports, oldest first" — the oldest is the one that
        # has been waiting longest, which is the one to look at.
        Index("ix_abuse_reports_status_created", "status", "created_at"),
        Index("ix_abuse_reports_target", "target_user_id"),
    )

    # Nullable so deleting an account does not erase reports about other people,
    # nor the reports made against them.
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), default=None
    )

    # Snapshots — see the module docstring on why these are copies.
    reporter_name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    target_name: Mapped[str] = mapped_column(String(80), default="", server_default="")

    # abuse | harassment | spam | inappropriate | other — kept as free text with a
    # validated enum at the API layer, matching how `plan` and `status` are done
    # elsewhere in this schema.
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    # What the reporter typed, plus any quoted line they attached.
    detail: Mapped[str | None] = mapped_column(Text, default=None)
    quoted_text: Mapped[str | None] = mapped_column(Text, default=None)

    status: Mapped[str] = mapped_column(
        String(16), default=ReportStatus.open, server_default="open", nullable=False
    )
    # Who closed it and what they decided. Empty until someone acts.
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    review_note: Mapped[str | None] = mapped_column(Text, default=None)
