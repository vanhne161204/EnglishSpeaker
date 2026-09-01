"""Data-access for room bans (docs/11_Security.md Step 4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.room import Room
from app.models.room_ban import RoomBan
from app.models.user import User


class RoomBanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, room_id: uuid.UUID, user_id: uuid.UUID) -> RoomBan | None:
        """The ban row for this pair, expired or not."""
        stmt = select(RoomBan).where(RoomBan.room_id == room_id, RoomBan.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def is_banned(self, room_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Whether a *live* ban applies. An expired row is not a ban.

        Expired rows are left in place rather than deleted on read: the history of
        "this person was banned from this room" is worth keeping, and a read path
        that writes is a read path that can deadlock.
        """
        now = datetime.now(UTC)
        stmt = select(RoomBan.id).where(
            RoomBan.room_id == room_id,
            RoomBan.user_id == user_id,
            or_(RoomBan.expires_at.is_(None), RoomBan.expires_at > now),
        )
        return (await self.session.execute(stmt)).first() is not None

    async def upsert(
        self,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        banned_by: uuid.UUID | None,
        reason: str | None,
        expires_at: datetime | None,
    ) -> RoomBan:
        """Ban, or replace an existing ban on the same pair.

        Re-banning updates rather than inserting, so a room never accumulates
        three rows that each have to be lifted separately.
        """
        existing = await self.get(room_id, user_id)
        if existing is not None:
            existing.banned_by = banned_by
            existing.reason = reason
            existing.expires_at = expires_at
            await self.session.flush()
            return existing

        ban = RoomBan(
            room_id=room_id,
            user_id=user_id,
            banned_by=banned_by,
            reason=reason,
            expires_at=expires_at,
        )
        self.session.add(ban)
        await self.session.flush()
        return ban

    async def lift(self, ban_id: uuid.UUID) -> RoomBan | None:
        """Remove a ban outright. Returns the row that was removed, or None."""
        ban = await self.session.get(RoomBan, ban_id)
        if ban is None:
            return None
        await self.session.delete(ban)
        await self.session.flush()
        return ban

    async def clear_room(self, room_id: uuid.UUID) -> None:
        """Drop every ban for a room (used when tearing a room down, and in tests)."""
        await self.session.execute(delete(RoomBan).where(RoomBan.room_id == room_id))

    async def list_active(
        self, limit: int = 100, offset: int = 0
    ) -> list[tuple[RoomBan, str | None, str | None]]:
        """(ban, room title, banned user's display name), newest first.

        Joined here rather than looked up per row: the admin queue would otherwise
        issue one query per ban to render a single page.
        """
        now = datetime.now(UTC)
        stmt = (
            select(RoomBan, Room.title, User.display_name)
            .join(Room, Room.id == RoomBan.room_id, isouter=True)
            .join(User, User.id == RoomBan.user_id, isouter=True)
            .where(or_(RoomBan.expires_at.is_(None), RoomBan.expires_at > now))
            .order_by(RoomBan.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(ban, title, name) for ban, title, name in rows]
