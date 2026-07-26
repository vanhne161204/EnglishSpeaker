"""Username/password authentication (PRD: optional login on the device profile).

Flow: ``register`` creates a user with a hashed password; ``login`` verifies the
password against the stored hash. Login is optional and gates nothing — it simply
binds a username to a persistent profile so a user can restore their identity
(e.g. on another device).

The raw password is never stored; see ``app.core.security``.
"""

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository


def _is_admin_username(username: str) -> bool:
    """Whether this username is on the configured admin allowlist."""
    return username in settings.admin_usernames


class UsernameTakenError(AppError):
    status_code = 409
    code = "username_taken"


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def register(
        self, username: str, password: str, display_name: str | None = None
    ) -> User:
        """Create an account. Fails if the username is already taken."""
        if await self.users.get_by_username(username) is not None:
            raise UsernameTakenError("That username is already taken.")
        user = User(
            username=username,
            display_name=(display_name or username).strip() or username,
            password_hash=hash_password(password),
            is_admin=_is_admin_username(username),
        )
        return await self.users.add(user)

    async def login(self, username: str, password: str) -> User:
        """Verify credentials and return the user.

        The same generic error is raised whether the username or the password is
        wrong, so an attacker cannot tell which usernames exist.
        """
        user = await self.users.get_by_username(username)
        if user is None or not user.password_hash:
            raise InvalidCredentialsError("Incorrect username or password.")
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Incorrect username or password.")
        # Keep admin rights in sync with the allowlist (promote/demote on login).
        desired_admin = _is_admin_username(username)
        if user.is_admin != desired_admin:
            user.is_admin = desired_admin
        return user
