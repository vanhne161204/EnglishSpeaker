"""IELTS band report endpoints — Coach Report layer 2 (docs §10.3.7, §10.5).

Every route filters on the **authenticated** user. A report is private to its
subject: a room member must not be able to read another member's bands by
guessing an id.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import build_llm
from app.ai.routing import AiTask
from app.api.deps import get_current_user
from app.core.exceptions import AppError
from app.db.session import get_session
from app.models.enums import ConversationMode, PlanTier
from app.models.user import User
from app.repositories.room import RoomRepository
from app.repositories.session_report import SessionReportRepository
from app.repositories.transcript import TranscriptRepository
from app.schemas.ielts import BandPoint, ReportMode, SessionReportRead
from app.services.ielts import (
    IeltsService,
    NotEnoughSpeech,
    ReportUnavailable,
)

router = APIRouter(prefix="/reports", tags=["reports"])

_MAX_SEGMENTS = 300


class NotEnoughSpeechError(AppError):
    status_code = 400
    code = "not_enough_speech"


class ReportUnavailableError(AppError):
    status_code = 503
    code = "report_unavailable"


@router.post(
    "/rooms/{room_id}",
    response_model=SessionReportRead,
    summary="Get my band report for this session",
)
async def build_report(
    room_id: uuid.UUID,
    mode: ReportMode = Query(default=ReportMode.conversation),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SessionReportRead:
    """Band my speaking in one session.

    The whole room's segments are loaded, but only mine are scored — a partner's
    line is context for "did you answer the question?", never graded and never
    stored (§10.3.0).
    """
    room = await RoomRepository(session).get(room_id)
    # Incognito: no partner context at all. The Fluency judgement is slightly
    # weaker, which is the right trade when the mode's whole promise is that
    # nothing about the other person persists (PRD §7.2).
    include_partner = not (room and room.mode == ConversationMode.incognito.value)

    segments = await TranscriptRepository(session).list_for_room(
        room_id, limit=_MAX_SEGMENTS
    )
    service = IeltsService(
        *build_llm(AiTask.ielts_report, PlanTier(user.plan), user.id, room_id),
        SessionReportRepository(session),
    )
    try:
        report = await service.build_report(
            user.id, segments, room_id=room_id, mode=mode, include_partner=include_partner
        )
    except NotEnoughSpeech as exc:
        raise NotEnoughSpeechError(str(exc)) from exc
    except ReportUnavailable as exc:
        raise ReportUnavailableError(str(exc)) from exc

    await session.commit()
    return SessionReportRead.model_validate(report)


@router.get(
    "/rooms/{room_id}",
    response_model=SessionReportRead | None,
    summary="My existing report for this session",
)
async def room_report(
    room_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SessionReportRead | None:
    """The stored report, or null. No AI call, so it is free to poll on mount."""
    report = await SessionReportRepository(session).latest_for_room(user.id, room_id)
    return SessionReportRead.model_validate(report) if report else None


@router.get(
    "/me/history",
    response_model=list[BandPoint],
    summary="My band over time",
)
async def band_history(
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[BandPoint]:
    """Oldest-first, ready to plot. Progress is what brings a learner back."""
    rows = await SessionReportRepository(session).history(user.id, limit)
    return [
        BandPoint(created_at=r.created_at, band_overall=r.band_overall, mode=r.mode)
        for r in rows
    ]
