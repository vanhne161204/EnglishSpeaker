"""AI voice coach endpoints (PRD §8.12, docs/08_API.md "AI Voice Coach").

The browser opens the Gemini Live session itself. These endpoints only issue the
one-use token, report the daily allowance, and close a session's books.
"""

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_voice_coach_service
from app.core.rate_limit import rate_limiter
from app.models.user import User
from app.schemas.voice_coach import (
    VoiceCoachUsage,
    VoiceSessionCreate,
    VoiceSessionEnded,
    VoiceSessionStarted,
)
from app.services.voice_coach import VoiceCoachService

router = APIRouter(prefix="/voice-coach", tags=["voice-coach"])


@router.get("/usage", response_model=VoiceCoachUsage, summary="My AI voice minutes for today")
async def usage(
    user: User = Depends(get_current_user),
    service: VoiceCoachService = Depends(get_voice_coach_service),
) -> VoiceCoachUsage:
    return await service.usage(user)


@router.post(
    "/sessions",
    response_model=VoiceSessionStarted,
    status_code=status.HTTP_201_CREATED,
    summary="Start a session: returns a one-use Gemini Live token",
    # Each start asks Google for a token. The allowance stops a learner from
    # talking too long; this stops a script from hammering the token endpoint.
    dependencies=[Depends(rate_limiter(10, 60))],
)
async def start_session(
    payload: VoiceSessionCreate,
    user: User = Depends(get_current_user),
    service: VoiceCoachService = Depends(get_voice_coach_service),
) -> VoiceSessionStarted:
    return await service.start(user, payload.topic_id)


@router.post(
    "/sessions/{session_id}/end",
    response_model=VoiceSessionEnded,
    summary="End a session and give back unused time",
)
async def end_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: VoiceCoachService = Depends(get_voice_coach_service),
) -> VoiceSessionEnded:
    return await service.end(user, session_id)
