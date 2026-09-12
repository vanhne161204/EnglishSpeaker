"""Admin endpoints for Shadowing video lessons (PRD §8.14 Phase 4,
docs/08_API.md "Admin — Shadowing videos")."""

import uuid

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_shadowing_video_admin_service, require_admin
from app.models.user import User
from app.schemas.shadowing import (
    ShadowingVideoAdminDetail,
    ShadowingVideoAdminRead,
    ShadowingVideoCreate,
    ShadowingVideoUpdate,
    VideoSegmentsSave,
)
from app.services.shadowing_video import ShadowingVideoAdminService

router = APIRouter(
    prefix="/admin/shadowing/videos", tags=["admin"], dependencies=[Depends(require_admin)]
)


@router.get(
    "", response_model=list[ShadowingVideoAdminRead], summary="All video lessons, drafts too"
)
async def list_videos(
    service: ShadowingVideoAdminService = Depends(get_shadowing_video_admin_service),
) -> list[ShadowingVideoAdminRead]:
    return await service.list()


@router.post(
    "",
    response_model=ShadowingVideoAdminDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Add a video lesson, as a draft",
)
async def create_video(
    payload: ShadowingVideoCreate,
    actor: User = Depends(require_admin),
    service: ShadowingVideoAdminService = Depends(get_shadowing_video_admin_service),
) -> ShadowingVideoAdminDetail:
    return await service.create(actor, payload)


@router.get(
    "/{video_id}",
    response_model=ShadowingVideoAdminDetail,
    summary="One video lesson with its sentences",
)
async def get_video(
    video_id: uuid.UUID,
    service: ShadowingVideoAdminService = Depends(get_shadowing_video_admin_service),
) -> ShadowingVideoAdminDetail:
    return await service.get(video_id)


@router.patch(
    "/{video_id}",
    response_model=ShadowingVideoAdminDetail,
    summary="Edit a video lesson, or publish it",
)
async def update_video(
    video_id: uuid.UUID,
    payload: ShadowingVideoUpdate,
    actor: User = Depends(require_admin),
    service: ShadowingVideoAdminService = Depends(get_shadowing_video_admin_service),
) -> ShadowingVideoAdminDetail:
    return await service.update(actor, video_id, payload)


@router.put(
    "/{video_id}/segments",
    response_model=ShadowingVideoAdminDetail,
    summary="Replace a video lesson's sentences and their times",
)
async def save_segments(
    video_id: uuid.UUID,
    payload: VideoSegmentsSave,
    actor: User = Depends(require_admin),
    service: ShadowingVideoAdminService = Depends(get_shadowing_video_admin_service),
) -> ShadowingVideoAdminDetail:
    return await service.save_segments(actor, video_id, payload)


@router.delete(
    "/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a video lesson and every try at it",
)
async def delete_video(
    video_id: uuid.UUID,
    actor: User = Depends(require_admin),
    service: ShadowingVideoAdminService = Depends(get_shadowing_video_admin_service),
) -> Response:
    await service.delete(actor, video_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
