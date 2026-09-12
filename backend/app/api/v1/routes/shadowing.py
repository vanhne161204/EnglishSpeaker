"""Shadowing endpoints (PRD §8.14, docs/08_API.md "Shadowing")."""

import uuid

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status

from app.api.deps import get_current_user, get_shadowing_service
from app.core.exceptions import BadRequestError
from app.core.rate_limit import rate_limiter
from app.models.user import User
from app.schemas.shadowing import (
    PronunciationResult,
    ShadowingAttemptCreate,
    ShadowingItemList,
    ShadowingResult,
    ShadowingVideoCard,
    ShadowingVideoLesson,
)
from app.services.shadowing import ShadowingService

router = APIRouter(prefix="/shadowing", tags=["shadowing"])

#: 30 s of 16 kHz mono 16-bit audio is 960 KB, plus the WAV header.
MAX_ASSESS_UPLOAD_BYTES = 1_000_000


@router.get(
    "/topics/{topic_id}/items",
    response_model=ShadowingItemList,
    summary="Sentences to shadow in one topic, with my best scores",
)
async def list_items(
    topic_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: ShadowingService = Depends(get_shadowing_service),
) -> ShadowingItemList:
    return await service.items(user, topic_id)


@router.get(
    "/topics/{topic_id}/items/{item_key}/audio",
    summary="The model voice for one sentence (audio/wav)",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}}, 304: {"description": "Not modified"}},
    # Serving a stored clip is cheap, but the first request for a sentence makes
    # one with TTS. This keeps a script from hammering either.
    dependencies=[Depends(rate_limiter(120, 60))],
)
async def item_audio(
    topic_id: uuid.UUID,
    item_key: str,
    request: Request,
    _: User = Depends(get_current_user),
    service: ShadowingService = Depends(get_shadowing_service),
) -> Response:
    clip = await service.clip(topic_id, item_key)
    # The URL stays the same when an admin edits the sentence, so the clip is
    # revalidated by content (its hash) rather than cached forever.
    etag = f'"{clip.text_hash}"'
    headers = {"ETag": etag, "Cache-Control": "private, max-age=86400"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=clip.data, media_type=clip.mime_type, headers=headers)


@router.get(
    "/videos",
    response_model=list[ShadowingVideoCard],
    summary="Published video lessons, with how many sentences I have tried",
)
async def list_videos(
    user: User = Depends(get_current_user),
    service: ShadowingService = Depends(get_shadowing_service),
) -> list[ShadowingVideoCard]:
    return await service.videos(user)


@router.get(
    "/videos/{video_id}/items",
    response_model=ShadowingVideoLesson,
    summary="One video lesson: its sentences and their times, with my best scores",
)
async def video_items(
    video_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: ShadowingService = Depends(get_shadowing_service),
) -> ShadowingVideoLesson:
    return await service.video_items(user, video_id)


@router.post(
    "/attempts",
    response_model=ShadowingResult,
    status_code=status.HTTP_201_CREATED,
    summary="Score one try at a sentence and keep it",
    dependencies=[Depends(rate_limiter(60, 60))],
)
async def create_attempt(
    payload: ShadowingAttemptCreate,
    user: User = Depends(get_current_user),
    service: ShadowingService = Depends(get_shadowing_service),
) -> ShadowingResult:
    return await service.record_attempt(user, payload)


@router.post(
    "/assess",
    response_model=PronunciationResult,
    summary="Deep pronunciation check of one try (Azure, Phase 2)",
    # Each call costs money; the daily allowance is the real cap, this stops a script.
    dependencies=[Depends(rate_limiter(20, 60))],
)
async def assess_pronunciation(
    item_key: str = Form(..., max_length=80),
    audio: UploadFile = File(...),
    # Exactly one: a topic sentence or a video sentence.
    topic_id: uuid.UUID | None = Form(None),
    video_id: uuid.UUID | None = Form(None),
    user: User = Depends(get_current_user),
    service: ShadowingService = Depends(get_shadowing_service),
) -> PronunciationResult:
    data = await audio.read(MAX_ASSESS_UPLOAD_BYTES + 1)
    if len(data) > MAX_ASSESS_UPLOAD_BYTES:
        raise BadRequestError("The recording is too long: 30 seconds at most.")
    return await service.assess(user, topic_id, item_key, data, video_id=video_id)
