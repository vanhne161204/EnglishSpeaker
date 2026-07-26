"""Translation endpoint — used by the in-room translator."""

from fastapi import APIRouter, Depends

from app.api.deps import get_translation_service
from app.schemas.translation import TranslateRequest, TranslateResult
from app.services.translation import TranslationService

router = APIRouter(prefix="/translate", tags=["translation"])


@router.post("", response_model=TranslateResult, summary="Translate text inside a room")
async def translate(
    payload: TranslateRequest,
    service: TranslationService = Depends(get_translation_service),
) -> TranslateResult:
    return await service.translate(payload)
