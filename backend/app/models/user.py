"""User model — a lightweight profile (PRD §9.1).

Identity is a display name plus learning preferences. Optional username/password
login layers on top: guests keep full function with no account, while a
registered user has a ``username`` and a bcrypt ``password_hash`` (never a raw
password) so they can restore their profile on another device.
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import UserRole
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Optional login credentials (PRD: optional auth on top of the device
    # profile). NULL for guests; unique when set. SQLite allows many NULLs.
    username: Mapped[str | None] = mapped_column(String(40), unique=True, default=None)
    # bcrypt hash of the password — never the raw value. NULL for guests.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    # What this user may do: "user" | "admin" (models.enums.UserRole).
    #
    # **This column is the only authority.** Admin used to be derived from the
    # username via an ADMIN_USERNAMES allowlist that was re-applied on every
    # login, so a grant or revoke made anywhere else was silently undone the next
    # time that person signed in. Nothing derives admin from a name any more: the
    # first admin is created deliberately with `scripts/grant_admin.py`, and
    # after that the admin panel is what changes this column.
    role: Mapped[str] = mapped_column(
        String(20), default=UserRole.user, server_default="user", nullable=False
    )
    # Set when an admin suspends the account. A suspended user cannot log in and
    # their existing token stops working on the next request — the check lives in
    # `get_current_user`, so it covers the WebSocket handshake too.
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Why, in the admin's words. Shown to the user on the login screen so a
    # suspension is not a silent, unexplained failure.
    suspended_reason: Mapped[str | None] = mapped_column(String(200), default=None)
    # Legacy: retained (nullable) so old rows and code keep working; no longer
    # used for login now that auth is username/password.
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, default=None)
    level: Mapped[str | None] = mapped_column(String(40), default=None)
    # Comma-separated interests (e.g. "travel,music") — kept simple for the MVP.
    interests: Mapped[str | None] = mapped_column(String(300), default=None)
    # Subscription plan: free | premium (validated against PlanTier at the API layer).
    plan: Mapped[str] = mapped_column(
        String(20), default="free", server_default="free", nullable=False
    )
