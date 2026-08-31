"""Data-access for sentence notes."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sentence_note import SentenceNote


class NoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, user_id: uuid.UUID) -> Sequence[SentenceNote]:
        """One learner's notes. Always scoped — there is no "list all"."""
        result = await self.session.execute(
            select(SentenceNote)
            .where(SentenceNote.user_id == user_id)
            .order_by(SentenceNote.created_at.desc())
        )
        return result.scalars().all()

    async def get(self, note_id: uuid.UUID, user_id: uuid.UUID) -> SentenceNote | None:
        """Fetch a note **only if it belongs to this learner**.

        Scoping here rather than in the service means a caller cannot edit or
        delete somebody else's note by guessing an id — the note simply is not
        found.
        """
        result = await self.session.execute(
            select(SentenceNote).where(
                SentenceNote.id == note_id, SentenceNote.user_id == user_id
            )
        )
        return result.scalars().first()

    async def count(self, user_id: uuid.UUID) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(SentenceNote)
                .where(SentenceNote.user_id == user_id)
            )
            or 0
        )

    async def add(self, note: SentenceNote) -> SentenceNote:
        self.session.add(note)
        await self.session.flush()
        return note

    async def delete(self, note: SentenceNote) -> None:
        await self.session.delete(note)
