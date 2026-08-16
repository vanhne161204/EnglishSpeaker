"""Business logic for topics."""

import uuid
from collections.abc import Sequence

from app.core.exceptions import ConflictError, NotFoundError
from app.models.topic import Topic
from app.repositories.category import CategoryRepository
from app.repositories.topic import TopicRepository
from app.schemas.topic import TopicCreate, TopicUpdate


class TopicService:
    def __init__(
        self, repository: TopicRepository, categories: CategoryRepository | None = None
    ) -> None:
        self.repository = repository
        # Optional so callers that never touch categories can stay lightweight.
        self.categories = categories

    async def list_topics(self, category_id: uuid.UUID | None = None) -> Sequence[Topic]:
        return await self.repository.list(category_id)

    async def get_topic(self, topic_id: uuid.UUID) -> Topic:
        topic = await self.repository.get(topic_id)
        if topic is None:
            raise NotFoundError("Topic not found")
        return topic

    async def create_topic(self, payload: TopicCreate) -> Topic:
        if await self.repository.get_by_slug(payload.slug):
            raise ConflictError(f"Topic with slug '{payload.slug}' already exists")
        await self._check_category(payload.category_id)
        return await self.repository.add(Topic(**payload.model_dump()))

    async def update_topic(self, topic_id: uuid.UUID, payload: TopicUpdate) -> Topic:
        topic = await self.get_topic(topic_id)
        changes = payload.model_dump(exclude_unset=True)
        if "category_id" in changes:
            await self._check_category(changes["category_id"])
        for field, value in changes.items():
            setattr(topic, field, value)
        return topic

    async def delete_topic(self, topic_id: uuid.UUID) -> None:
        topic = await self.get_topic(topic_id)
        await self.repository.delete(topic)

    async def _check_category(self, category_id: uuid.UUID | None) -> None:
        """Reject an unknown category — SQLite doesn't enforce FKs by default."""
        if category_id is None or self.categories is None:
            return
        if await self.categories.get(category_id) is None:
            raise NotFoundError("Category not found")
