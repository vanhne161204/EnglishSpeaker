"""Data-access for sentence notes."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sentence_note import SentenceNote


class NoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> Sequence[SentenceNote]:
        result = await self.session.execute(
            select(SentenceNote).order_by(SentenceNote.created_at.desc())
        )
        return result.scalars().all()

    async def get(self, note_id: uuid.UUID) -> SentenceNote | None:
        return await self.session.get(SentenceNote, note_id)

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(SentenceNote)) or 0

    async def add(self, note: SentenceNote) -> SentenceNote:
        self.session.add(note)
        await self.session.flush()
        return note

    async def delete(self, note: SentenceNote) -> None:
        await self.session.delete(note)
