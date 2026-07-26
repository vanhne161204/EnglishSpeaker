"""Topic endpoints."""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, status

from app.api.deps import get_topic_service, require_admin
from app.models.topic import Topic
from app.models.user import User
from app.schemas.topic import TopicCreate, TopicRead, TopicUpdate
from app.services.topic import TopicService

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=list[TopicRead], summary="List topics")
async def list_topics(service: TopicService = Depends(get_topic_service)) -> Sequence[Topic]:
    # ORM objects are serialized to TopicRead via ``response_model``.
    return await service.list_topics()


@router.post(
    "",
    response_model=TopicRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a topic (admin)",
)
async def create_topic(
    payload: TopicCreate,
    service: TopicService = Depends(get_topic_service),
    _: User = Depends(require_admin),
) -> Topic:
    return await service.create_topic(payload)


@router.get("/{topic_id}", response_model=TopicRead, summary="Get a topic")
async def get_topic(
    topic_id: uuid.UUID,
    service: TopicService = Depends(get_topic_service),
) -> Topic:
    return await service.get_topic(topic_id)


@router.patch("/{topic_id}", response_model=TopicRead, summary="Edit a topic (admin)")
async def update_topic(
    topic_id: uuid.UUID,
    payload: TopicUpdate,
    service: TopicService = Depends(get_topic_service),
    _: User = Depends(require_admin),
) -> Topic:
    return await service.update_topic(topic_id, payload)


@router.delete(
    "/{topic_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a topic (admin)",
)
async def delete_topic(
    topic_id: uuid.UUID,
    service: TopicService = Depends(get_topic_service),
    _: User = Depends(require_admin),
) -> None:
    await service.delete_topic(topic_id)
