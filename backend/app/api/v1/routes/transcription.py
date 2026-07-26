"""Speech-to-Text endpoint (PRD §8.9)."""

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_transcription_service
from app.schemas.transcription import TranscriptionResult
from app.services.transcription import TranscriptionService

router = APIRouter(prefix="/transcribe", tags=["speech-to-text"])


@router.post("", response_model=TranscriptionResult, summary="Transcribe recorded audio")
async def transcribe(
    audio: UploadFile = File(...),
    language: str | None = Form(default=None),
    service: TranscriptionService = Depends(get_transcription_service),
) -> TranscriptionResult:
    data = await audio.read()
    return await service.transcribe(data, language)
