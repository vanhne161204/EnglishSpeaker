"""Sentence-note endpoints.

Every route is scoped to the authenticated caller. Notes used to have no owner
at all, so one learner could read and delete another's saved sentences
(docs/11_Security.md §11.4).
"""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_note_service
from app.models.sentence_note import SentenceNote
from app.models.user import User
from app.schemas.note import NoteCreate, NoteRead, NoteUpdate
from app.services.note import NoteService

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("", response_model=list[NoteRead], summary="List sentence notes")
async def list_notes(
    user: User = Depends(get_current_user),
    service: NoteService = Depends(get_note_service),
) -> Sequence[SentenceNote]:
    return await service.list_notes(user.id)


@router.post(
    "",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save a sentence note",
)
async def create_note(
    payload: NoteCreate,
    user: User = Depends(get_current_user),
    service: NoteService = Depends(get_note_service),
) -> SentenceNote:
    return await service.create_note(user.id, payload)


@router.patch("/{note_id}", response_model=NoteRead, summary="Edit a sentence note")
async def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdate,
    user: User = Depends(get_current_user),
    service: NoteService = Depends(get_note_service),
) -> SentenceNote:
    return await service.update_note(note_id, user.id, payload)


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a sentence note",
)
async def delete_note(
    note_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: NoteService = Depends(get_note_service),
) -> None:
    await service.delete_note(note_id, user.id)
