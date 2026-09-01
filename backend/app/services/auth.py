"""Username/password authentication (PRD: optional login on the device profile).

Flow: ``register`` creates a user with a hashed password; ``login`` verifies the
password against the stored hash. Login is optional and gates nothing — it simply
binds a username to a persistent profile so a user can restore their identity
(e.g. on another device).

The raw password is never stored; see ``app.core.security``.
"""

from app.core.exceptions import AppError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository


class UsernameTakenError(AppError):
    status_code = 409
    code = "username_taken"


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"


class AccountSuspendedError(AppError):
    """The credentials were right, but the account is switched off.

    Deliberately distinct from ``InvalidCredentialsError``: telling someone their
    password is wrong when it is not sends them into a password-reset loop for a
    problem no reset can fix.
    """

    status_code = 403
    code = "account_suspended"


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def register(self, username: str, password: str, display_name: str | None = None) -> User:
        """Create an account. Fails if the username is already taken."""
        if await self.users.get_by_username(username) is not None:
            raise UsernameTakenError("That username is already taken.")
        user = User(
            username=username,
            display_name=(display_name or username).strip() or username,
            password_hash=hash_password(password),
        )
        return await self.users.add(user)

    async def login(self, username: str, password: str) -> User:
        """Verify credentials and return the user.

        The same generic error is raised whether the username or the password is
        wrong, so an attacker cannot tell which usernames exist.

        Raises:
            InvalidCredentialsError: no such user, or the password is wrong.
            AccountSuspendedError: the account exists but an admin switched it off.
        """
        user = await self.users.get_by_username(username)
        if user is None or not user.password_hash:
            raise InvalidCredentialsError("Incorrect username or password.")
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Incorrect username or password.")
        if user.suspended_at is not None:
            raise AccountSuspendedError(user.suspended_reason or "This account has been suspended.")

        # NOTE: nothing here touches `role`, and nothing anywhere derives it
        # from a username. Admin used to be re-applied from an ADMIN_USERNAMES
        # allowlist on every login, so registering the configured name handed
        # out the keys and any grant made in the panel silently reverted.
        # The `users.role` column is the only authority (docs/11_Security.md
        # 11.2); the first admin is created with `scripts/grant_admin.py`.
        return user
