"""Password hashing for username/password auth.

We never store a raw password. Registration hashes it with bcrypt (a slow,
salted one-way function), and login re-hashes the input and compares.

We call the ``bcrypt`` library directly rather than through passlib: passlib
1.7.4 (unmaintained since 2020) crashes on import with bcrypt 5.x because its
self-test feeds bcrypt an over-length string that modern bcrypt rejects.

bcrypt only looks at the first 72 bytes of a password, so we truncate to 72
bytes before hashing *and* verifying — consistently, so the check still matches.
The schema also caps password length; this is defence in depth (and handles
multi-byte characters, where 72 chars can exceed 72 bytes).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

_MAX_BCRYPT_BYTES = 72


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_BCRYPT_BYTES]


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash safe to store in the database."""
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if ``password`` matches the stored ``password_hash``."""
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("ascii"))
    except ValueError:
        # Malformed/legacy hash — treat as a failed match rather than a 500.
        return False


# --- Session tokens (JWT) --------------------------------------------------
#
# Login/register hand back a signed JWT instead of the raw user id. Because it's
# signed with the server secret and carries an expiry, clients can no longer
# forge a token by guessing a UUID — the previous, critical impersonation hole.


def create_access_token(user_id: uuid.UUID | str, is_admin: bool) -> str:
    """Create a signed, expiring session token for a user."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),  # subject = the user's id
        "adm": bool(is_admin),  # convenience claim; authority is re-checked server-side
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Verify a session token's signature and expiry; return its claims or None."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        # Bad signature, tampered payload, expired, or malformed — all invalid.
        return None
