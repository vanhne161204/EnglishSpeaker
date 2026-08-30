"""Transcript read/delete endpoints (PRD §8.9).

The live script arrives over the room WebSocket; these serve the cases a socket
cannot: reviewing a finished session, reading your own speaking history, and
deleting it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.repositories.transcript import TranscriptRepository
from app.schemas.transcript import TranscriptPage, TranscriptSegmentRead

router = APIRouter(prefix="/transcripts", tags=["transcripts"])

_MAX_LIMIT = 200


def _page(segments) -> TranscriptPage:
    """Wrap rows as a page, with the cursor for the previous (older) page."""
    items = [TranscriptSegmentRead.model_validate(s) for s in segments]
    # Segments come back oldest-first, so the oldest one is the next cursor.
    return TranscriptPage(
        segments=items,
        next_before=items[0].spoken_at if items else None,
    )


@router.get(
    "/rooms/{room_id}",
    response_model=TranscriptPage,
    summary="The script of one room",
)
async def room_transcript(
    room_id: uuid.UUID,
    speaker_id: uuid.UUID | None = Query(
        default=None, description="Only this speaker's lines."
    ),
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    before: datetime | None = Query(
        default=None, description="Return segments spoken before this time (paging)."
    ),
    session: AsyncSession = Depends(get_session),
) -> TranscriptPage:
    segments = await TranscriptRepository(session).list_for_room(
        room_id, limit=limit, before=before, user_id=speaker_id
    )
    return _page(segments)


@router.get(
    "/me",
    response_model=TranscriptPage,
    summary="Everything I have said, across every room",
)
async def my_transcript(
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    before: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TranscriptPage:
    """Filtered on the **authenticated** user, never a query parameter — a
    transcript is private to its speaker, and an id in the URL would let anyone
    read anyone."""
    segments = await TranscriptRepository(session).list_for_user(
        user.id, limit=limit, before=before
    )
    return _page(segments)


@router.delete(
    "/me",
    summary="Delete my transcript",
    status_code=200,
)
async def delete_my_transcript(
    room_id: uuid.UUID | None = Query(
        default=None, description="Limit the deletion to one room."
    ),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """Erase what I said — PRD §17 asks whether learners may do this; yes.

    Scoped to the caller's own rows. A learner can delete their own speech, never
    anybody else's, so one person cannot rewrite a shared conversation.
    """
    deleted = await TranscriptRepository(session).delete_for_user(user.id, room_id)
    await session.commit()
    return {"deleted": deleted}
