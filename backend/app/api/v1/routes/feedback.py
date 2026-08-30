"""Coach Report layer 1 endpoints (docs/10_AI_Design.md §10.3, §10.5).

Assessment runs on demand rather than automatically: the learner asks for it
after a session. Live correction while someone is still speaking would destroy
the confidence the whole product is trying to build (PRD §14.7).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import build_llm
from app.ai.routing import AiTask
from app.api.deps import get_current_user
from app.core.exceptions import AppError
from app.db.session import get_session
from app.models.enums import PlanTier
from app.models.user import User
from app.repositories.feedback import FeedbackRepository
from app.repositories.transcript import TranscriptRepository
from app.schemas.feedback import (
    FeedbackSummary,
    MistakeCount,
    SentenceFeedbackRead,
)
from app.services.feedback import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])

#: Most a single request will grade. A long session is still bounded, so one
#: click cannot trigger an unbounded run of API calls.
_MAX_SEGMENTS = 200


class NothingToAssessError(AppError):
    status_code = 400
    code = "nothing_to_assess"


@router.post(
    "/rooms/{room_id}",
    response_model=list[SentenceFeedbackRead],
    summary="Check what I said in this session",
)
async def assess_room(
    room_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SentenceFeedbackRead]:
    """Grade **my own** speech from one room.

    Scoped to the authenticated user's segments (docs §10.3.0): a learner is
    graded on what they said, never on what a partner said, and never gets a
    report about somebody else.
    """
    segments = await TranscriptRepository(session).list_for_room(
        room_id, limit=_MAX_SEGMENTS, user_id=user.id
    )
    if not segments:
        raise NothingToAssessError("You didn't say anything in this session yet.")

    tier = PlanTier(user.plan)
    llm, route = build_llm(AiTask.sentence_check, tier, user.id, room_id)
    service = FeedbackService(llm, route, FeedbackRepository(session))

    rows = await service.assess(user.id, segments, level=user.level, room_id=room_id)
    await session.commit()

    if not rows:
        raise NothingToAssessError(
            "Nothing to check yet — say a few full sentences and try again."
        )
    return [SentenceFeedbackRead.model_validate(r) for r in rows]


@router.get(
    "/rooms/{room_id}",
    response_model=list[SentenceFeedbackRead],
    summary="My report for one session",
)
async def room_report(
    room_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SentenceFeedbackRead]:
    rows = await FeedbackRepository(session).list_for_room(user.id, room_id)
    return [SentenceFeedbackRead.model_validate(r) for r in rows]


@router.get(
    "/me",
    response_model=list[SentenceFeedbackRead],
    summary="Everything the coach has found for me",
)
async def my_feedback(
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SentenceFeedbackRead]:
    rows = await FeedbackRepository(session).list_for_user(user.id, limit, before)
    return [SentenceFeedbackRead.model_validate(r) for r in rows]


@router.get(
    "/me/summary",
    response_model=FeedbackSummary,
    summary="What I keep getting wrong",
)
async def my_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FeedbackSummary:
    """*"You used the wrong past tense 14 times this week."*

    Pure SQL over rows we already have — **no AI call**, so this costs nothing
    to show and can sit on the dashboard (§10.5).
    """
    repo = FeedbackRepository(session)
    checked, with_errors, average = await repo.stats(user.id)
    return FeedbackSummary(
        sentences_checked=checked,
        with_errors=with_errors,
        average_score=round(average, 1),
        top_mistakes=[
            MistakeCount(kind=kind, count=count)
            for kind, count in await repo.top_mistakes(user.id)
        ],
    )
