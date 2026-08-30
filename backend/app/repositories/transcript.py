"""Data-access for transcript segments (PRD §8.9)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transcript import TranscriptSegment


class TranscriptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, segment: TranscriptSegment) -> TranscriptSegment:
        self.session.add(segment)
        await self.session.flush()
        return segment

    async def list_for_room(
        self,
        room_id: uuid.UUID,
        limit: int = 50,
        before: datetime | None = None,
        user_id: uuid.UUID | None = None,
    ) -> Sequence[TranscriptSegment]:
        """The newest ``limit`` segments, returned **oldest-first**.

        Paging runs backwards through time (``before``) because that is how a
        transcript is read: you land on the end and scroll up into history.
        """
        stmt = select(TranscriptSegment).where(TranscriptSegment.room_id == room_id)
        if user_id is not None:
            stmt = stmt.where(TranscriptSegment.user_id == user_id)
        if before is not None:
            stmt = stmt.where(TranscriptSegment.spoken_at < before)
        stmt = stmt.order_by(TranscriptSegment.spoken_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(reversed(rows))

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int = 50, before: datetime | None = None
    ) -> Sequence[TranscriptSegment]:
        """One learner's own speech across every room — "what did I say?"."""
        stmt = select(TranscriptSegment).where(TranscriptSegment.user_id == user_id)
        if before is not None:
            stmt = stmt.where(TranscriptSegment.spoken_at < before)
        stmt = stmt.order_by(TranscriptSegment.spoken_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(reversed(rows))

    async def count_for_user_in_room(self, room_id: uuid.UUID, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(TranscriptSegment)
            .where(
                TranscriptSegment.room_id == room_id,
                TranscriptSegment.user_id == user_id,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def delete_for_user(
        self, user_id: uuid.UUID, room_id: uuid.UUID | None = None
    ) -> int:
        """Erase a learner's own transcript (PRD §17: "can users delete these?").

        Scoped to one user always — a learner may delete what they said, never
        what anybody else said.
        """
        stmt = delete(TranscriptSegment).where(TranscriptSegment.user_id == user_id)
        if room_id is not None:
            stmt = stmt.where(TranscriptSegment.room_id == room_id)
        return int((await self.session.execute(stmt)).rowcount or 0)
