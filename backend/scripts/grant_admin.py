"""Grant or revoke admin on an account, from the server.

This is how the **first** admin comes to exist. There is deliberately no
allowlist, no environment variable, and no "the first person to register wins":
admin used to be derived from the username via ``ADMIN_USERNAMES``, which meant
anyone who guessed the configured name and registered it got the keys, and any
grant made in the admin panel was undone at that person's next login.

After the first admin exists, use the admin panel. It records who changed what
in ``admin_audit_log``; this script cannot, because it runs with no actor.

Usage (on the server, inside the API container):

    docker compose --env-file .env.prod -f docker-compose.prod.yml \\
        run --rm api python -m scripts.grant_admin alice

    # take it away again
    ... run --rm api python -m scripts.grant_admin alice --revoke

    # see who has it
    ... run --rm api python -m scripts.grant_admin --list

Locally:

    cd backend && python -m scripts.grant_admin alice
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.enums import UserRole
from app.models.user import User


async def _list_admins() -> int:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(User).where(User.role == UserRole.admin).order_by(User.created_at)
            )
        ).scalars()
        admins = list(rows)

    if not admins:
        # Worth shouting about: nobody can reach the admin panel at all.
        print("No admins. Run this script with a username to create one.")
        return 1

    print(f"{len(admins)} admin(s):")
    for user in admins:
        suspended = " [SUSPENDED]" if user.suspended_at else ""
        print(f"  {user.username or '(no username)'} - {user.display_name}{suspended}")
    return 0


async def _set_role(username: str, role: UserRole) -> int:
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.username == username.lower().strip()))
        ).scalar_one_or_none()

        if user is None:
            print(f"No account with username {username!r}.", file=sys.stderr)
            print("They must register first; this script only changes an existing account.")
            return 1

        if user.role == role:
            print(f"{username} is already {role.value}. Nothing to do.")
            return 0

        # Refuse to remove the last admin, the same rule the admin panel enforces
        # — otherwise this script becomes the way to lock everyone out.
        if user.role == UserRole.admin and role != UserRole.admin:
            remaining = (
                await session.execute(select(User).where(User.role == UserRole.admin))
            ).scalars()
            if len([u for u in remaining if u.id != user.id]) == 0:
                print(
                    f"{username} is the only admin. Promote someone else first.",
                    file=sys.stderr,
                )
                return 1

        was = user.role
        user.role = role
        await session.commit()
        print(f"{username}: {was} -> {role.value}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Grant or revoke admin on an account.")
    parser.add_argument("username", nargs="?", help="the account to change")
    parser.add_argument(
        "--revoke", action="store_true", help="demote to an ordinary user instead"
    )
    parser.add_argument("--list", action="store_true", help="list current admins and exit")
    args = parser.parse_args()

    if args.list:
        return asyncio.run(_list_admins())
    if not args.username:
        parser.error("give a username, or --list")

    role = UserRole.user if args.revoke else UserRole.admin
    return asyncio.run(_set_role(args.username, role))


if __name__ == "__main__":
    raise SystemExit(main())
