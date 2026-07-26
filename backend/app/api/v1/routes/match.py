"""Matchmaking endpoints (PRD §8.4, §8.5).

A match resolves to a room to join, so both endpoints return ``RoomRead``.
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_match_service
from app.models.room import Room
from app.schemas.match import MatchRequest
from app.schemas.room import RoomRead
from app.services.match import MatchService

router = APIRouter(prefix="/match", tags=["match"])


@router.post("/one", response_model=RoomRead, summary="Match into a 1-on-1 room")
async def match_one(
    payload: MatchRequest,
    service: MatchService = Depends(get_match_service),
) -> Room:
    return await service.match_one(payload)


@router.post("/random", response_model=RoomRead, summary="Quick random match")
async def random_match(
    payload: MatchRequest,
    service: MatchService = Depends(get_match_service),
) -> Room:
    return await service.random_match(payload)
