"""Data-access for rooms."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ConversationMode, RoomKind
from app.models.room import Room


class RoomRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        mode: ConversationMode | None = None,
        kind: RoomKind | None = None,
    ) -> Sequence[Room]:
        stmt = select(Room).where(Room.status == "open")
        if mode is not None:
            stmt = stmt.where(Room.mode == mode.value)
        if kind is not None:
            stmt = stmt.where(Room.kind == kind.value)
        stmt = stmt.order_by(Room.created_at)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get(self, room_id: uuid.UUID) -> Room | None:
        return await self.session.get(Room, room_id)

    async def find_open_match(
        self,
        mode: ConversationMode,
        kind: RoomKind | None = None,
        topic: str | None = None,
        level: str | None = None,
    ) -> Room | None:
        """An open room in the same mode with a free seat (most-filled first).

        Optional ``topic`` / ``level`` narrow the search; the match service calls
        this in priority order. Preferring the most-filled room keeps conversations
        social rather than scattering users across many empty rooms.
        """
        stmt = select(Room).where(
            Room.status == "open",
            Room.mode == mode.value,
            Room.participant_count < Room.capacity,
        )
        if kind is not None:
            stmt = stmt.where(Room.kind == kind.value)
        if topic is not None:
            stmt = stmt.where(Room.topic == topic)
        if level is not None:
            stmt = stmt.where(Room.level == level)
        stmt = stmt.order_by(Room.participant_count.desc(), Room.created_at)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(Room)) or 0

    async def delete(self, room: Room) -> None:
        """Remove a room. Cascades to its messages, participants, transcript and
        bans; reports, feedback and AI usage keep their rows with a NULL room."""
        await self.session.delete(room)
        await self.session.flush()

    async def add(self, room: Room) -> Room:
        self.session.add(room)
        await self.session.flush()
        return room
