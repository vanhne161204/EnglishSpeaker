"""Business logic for sentence notes."""

import uuid
from collections.abc import Sequence

from app.core.exceptions import NotFoundError
from app.models.sentence_note import SentenceNote
from app.repositories.note import NoteRepository
from app.schemas.note import NoteCreate, NoteUpdate


class NoteService:
    def __init__(self, repository: NoteRepository) -> None:
        self.repository = repository

    async def list_notes(self, user_id: uuid.UUID) -> Sequence[SentenceNote]:
        return await self.repository.list(user_id)

    async def get_note(self, note_id: uuid.UUID, user_id: uuid.UUID) -> SentenceNote:
        """A note belonging to somebody else is "not found", not "forbidden".

        403 would confirm the note exists, which leaks that somebody saved that
        sentence. 404 tells a prober nothing.
        """
        note = await self.repository.get(note_id, user_id)
        if note is None:
            raise NotFoundError("Note not found")
        return note

    async def create_note(self, user_id: uuid.UUID, payload: NoteCreate) -> SentenceNote:
        return await self.repository.add(
            SentenceNote(user_id=user_id, **payload.model_dump())
        )

    async def update_note(
        self, note_id: uuid.UUID, user_id: uuid.UUID, payload: NoteUpdate
    ) -> SentenceNote:
        note = await self.get_note(note_id, user_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(note, field, value)
        return note

    async def delete_note(self, note_id: uuid.UUID, user_id: uuid.UUID) -> None:
        note = await self.get_note(note_id, user_id)
        await self.repository.delete(note)
