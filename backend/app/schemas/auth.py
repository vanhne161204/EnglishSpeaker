"""Username/password auth schemas.

Login is optional on top of the device profile: a user can claim/restore a
persistent identity with a username and password. Guests keep full function
without ever registering.
"""

import re

from pydantic import BaseModel, Field, field_validator

from app.schemas.user import UserRead

_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,40}$")


def normalize_username(raw: str) -> str:
    """Lower-case and validate a username so the same name maps to one account.

    Allowed: 3–40 chars, lowercase letters, digits, and underscore. Callers get
    a clear error otherwise (surfaced as a 422 by FastAPI).
    """
    value = raw.strip().lower()
    if not _USERNAME_RE.match(value):
        raise ValueError("Username must be 3–40 letters, numbers, or underscores")
    return value


class RegisterRequest(BaseModel):
    username: str
    # bcrypt ignores bytes past 72, so cap there to avoid silent truncation.
    password: str = Field(min_length=8, max_length=72)
    # Optional public name shown in rooms; defaults to the username if omitted.
    display_name: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("username")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_username(v)


class LoginRequest(BaseModel):
    username: str
    password: str = Field(min_length=1, max_length=72)

    @field_validator("username")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_username(v)


class AuthResult(BaseModel):
    user: UserRead
    # Opaque session token. The demo identifies by user id and gates nothing, so
    # this is forward-compat scaffolding (swap for a real JWT when auth lands).
    token: str
