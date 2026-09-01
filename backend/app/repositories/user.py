"""Data-access for users."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.message import Message
from app.models.transcript import TranscriptSegment
from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
        await self.session.flush()

    # --- admin panel -------------------------------------------------------

    async def search(
        self,
        query: str | None = None,
        *,
        role: str | None = None,
        plan: str | None = None,
        suspended: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        """Filtered page of accounts, newest first.

        Search matches username OR display name, case-insensitively — an admin
        looking someone up rarely knows which of the two they were given.
        """
        stmt = select(User)
        stmt = _apply_filters(stmt, query, role, plan, suspended)
        stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count(
        self,
        query: str | None = None,
        *,
        role: str | None = None,
        plan: str | None = None,
        suspended: bool | None = None,
    ) -> int:
        """Total matching the same filters — the page needs a real total, not
        "50+", or nobody can tell whether they are looking at everyone."""
        stmt = select(func.count()).select_from(User)
        stmt = _apply_filters(stmt, query, role, plan, suspended)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_admins(self) -> int:
        """Guards the "you cannot remove the last admin" rule."""
        stmt = select(func.count()).select_from(User).where(User.role == UserRole.admin)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_since(self, since: datetime) -> int:
        """New accounts since a date — the only growth number worth a headline."""
        stmt = select(func.count()).select_from(User).where(User.created_at >= since)
        return int((await self.session.execute(stmt)).scalar_one())

    async def activity(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        """``{user_id: (messages sent, transcript lines spoken)}`` for one page.

        Two aggregate queries for the whole page rather than two per row: this is
        the difference between 2 queries and 100 when rendering a list of 50.
        """
        if not user_ids:
            return {}

        counts: dict[uuid.UUID, tuple[int, int]] = dict.fromkeys(user_ids, (0, 0))

        said = await self.session.execute(
            select(Message.user_id, func.count())
            .where(Message.user_id.in_(user_ids))
            .group_by(Message.user_id)
        )
        for uid, n in said.all():
            if uid in counts:
                counts[uid] = (int(n), counts[uid][1])

        spoke = await self.session.execute(
            select(TranscriptSegment.user_id, func.count())
            .where(TranscriptSegment.user_id.in_(user_ids))
            .group_by(TranscriptSegment.user_id)
        )
        for uid, n in spoke.all():
            if uid in counts:
                counts[uid] = (counts[uid][0], int(n))

        return counts


def _apply_filters(
    stmt: Select[Any],
    query: str | None,
    role: str | None,
    plan: str | None,
    suspended: bool | None,
) -> Select[Any]:
    """Shared WHERE clause so `search` and `count` can never drift apart.

    They must agree: a total computed with different filters than the rows is a
    pager that lies.
    """
    if query:
        like = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.username).like(like),
                func.lower(User.display_name).like(like),
            )
        )
    if role:
        stmt = stmt.where(User.role == role)
    if plan:
        stmt = stmt.where(User.plan == plan)
    if suspended is True:
        stmt = stmt.where(User.suspended_at.is_not(None))
    elif suspended is False:
        stmt = stmt.where(User.suspended_at.is_(None))
    return stmt
