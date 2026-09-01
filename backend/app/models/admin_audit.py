"""AdminAuditLog model — every privileged action, and who took it.

Boring until the first time it matters. An admin panel can promote accounts,
change plans, suspend people and read private practice data; without a record,
"who suspended this user and why" has no answer, and neither does "did anyone
look at my transcripts".

This is append-only. Nothing in the application updates or deletes a row — the
API exposes reads only. That is the entire point of an audit log, and the moment
it becomes editable it stops being evidence.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AdminAuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_audit_log"

    __table_args__ = (Index("ix_admin_audit_created_at", "created_at"),)

    # Nullable, and the name is snapshotted, so deleting an admin account does
    # not erase the trail of what that admin did.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    actor_name: Mapped[str] = mapped_column(String(80), default="", server_default="")

    # e.g. "user.promote", "user.suspend", "report.resolve", "ban.lift".
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    # What it was done to: "user" | "report" | "ban" | "room".
    target_type: Mapped[str] = mapped_column(String(24), default="", server_default="")
    target_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    target_name: Mapped[str] = mapped_column(String(80), default="", server_default="")

    # Human-readable summary of what changed, e.g. "plan free -> premium".
    detail: Mapped[str | None] = mapped_column(Text, default=None)
