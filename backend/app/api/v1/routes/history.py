"""Practice history (PRD §8.13): the conversations a learner joined.

Read-only and free: it shows saved results and never calls the AI. The learner
asks for new feedback from the room's history page, through the existing
feedback and report endpoints.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.repositories.history import HistoryRepository
from app.schemas.history import HistoryItem

router = APIRouter(prefix="/history", tags=["history"])


@router.get(
    "/me",
    response_model=list[HistoryItem],
    summary="The rooms I joined, with my own feedback",
)
async def my_history(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[HistoryItem]:
    """Always the caller's own history. There is no user id to pass: taking one
    from the URL would let anyone read anyone's (docs/11_Security.md §11.4)."""
    return await HistoryRepository(session).for_user(user.id, limit)
