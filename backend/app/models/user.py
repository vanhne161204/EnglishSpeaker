"""User model — a lightweight profile (PRD §9.1).

Identity is a display name plus learning preferences. Optional username/password
login layers on top: guests keep full function with no account, while a
registered user has a ``username`` and a bcrypt ``password_hash`` (never a raw
password) so they can restore their profile on another device.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Optional login credentials (PRD: optional auth on top of the device
    # profile). NULL for guests; unique when set. SQLite allows many NULLs.
    username: Mapped[str | None] = mapped_column(String(40), unique=True, default=None)
    # bcrypt hash of the password — never the raw value. NULL for guests.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    # Admin flag (PRD §9.2): only admins may manage topics/learning content.
    # Set from the ADMIN_USERNAMES allowlist on register/login (see AuthService).
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
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
