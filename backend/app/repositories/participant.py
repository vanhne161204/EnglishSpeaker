"""Data-access for room participants."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.participant import RoomParticipant


class ParticipantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(
        self, room_id: uuid.UUID, user_id: uuid.UUID
    ) -> RoomParticipant | None:
        result = await self.session.execute(
            select(RoomParticipant).where(
                RoomParticipant.room_id == room_id,
                RoomParticipant.user_id == user_id,
                RoomParticipant.left_at.is_(None),
            )
        )
        return result.scalars().first()

    async def list_active(self, room_id: uuid.UUID) -> Sequence[RoomParticipant]:
        result = await self.session.execute(
            select(RoomParticipant)
            .where(RoomParticipant.room_id == room_id, RoomParticipant.left_at.is_(None))
            .order_by(RoomParticipant.created_at)
        )
        return result.scalars().all()

    async def add(self, participant: RoomParticipant) -> RoomParticipant:
        self.session.add(participant)
        await self.session.flush()
        return participant
