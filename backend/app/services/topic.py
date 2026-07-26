"""Business logic for topics."""

import uuid
from collections.abc import Sequence

from app.core.exceptions import ConflictError, NotFoundError
from app.models.topic import Topic
from app.repositories.topic import TopicRepository
from app.schemas.topic import TopicCreate, TopicUpdate


class TopicService:
    def __init__(self, repository: TopicRepository) -> None:
        self.repository = repository

    async def list_topics(self) -> Sequence[Topic]:
        return await self.repository.list()

    async def get_topic(self, topic_id: uuid.UUID) -> Topic:
        topic = await self.repository.get(topic_id)
        if topic is None:
            raise NotFoundError("Topic not found")
        return topic

    async def create_topic(self, payload: TopicCreate) -> Topic:
        if await self.repository.get_by_slug(payload.slug):
            raise ConflictError(f"Topic with slug '{payload.slug}' already exists")
        return await self.repository.add(Topic(**payload.model_dump()))

    async def update_topic(self, topic_id: uuid.UUID, payload: TopicUpdate) -> Topic:
        topic = await self.get_topic(topic_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(topic, field, value)
        return topic

    async def delete_topic(self, topic_id: uuid.UUID) -> None:
        topic = await self.get_topic(topic_id)
        await self.repository.delete(topic)
