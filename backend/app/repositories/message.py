"""Data-access for chat messages."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_room(self, room_id: uuid.UUID, limit: int = 100) -> Sequence[Message]:
        # Newest ``limit`` rows, returned oldest-first so the client can append.
        result = await self.session.execute(
            select(Message)
            .where(Message.room_id == room_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def add(self, message: Message) -> Message:
        self.session.add(message)
        await self.session.flush()
        return message
