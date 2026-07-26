"""AI conversation-help endpoint — the in-room coach (PRD §8.8)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_assistant_service
from app.schemas.assist import AssistRequest, AssistResult
from app.services.assistant import AssistantService

router = APIRouter(prefix="/assist", tags=["assist"])


@router.post("", response_model=AssistResult, summary="Improve a sentence or suggest a reply")
async def assist(
    payload: AssistRequest,
    service: AssistantService = Depends(get_assistant_service),
) -> AssistResult:
    return await service.assist(payload)
