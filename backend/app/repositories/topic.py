"""Data-access for topics."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.topic import Topic


class TopicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, category_id: uuid.UUID | None = None) -> Sequence[Topic]:
        stmt = select(Topic)
        if category_id is not None:
            stmt = stmt.where(Topic.category_id == category_id)
        # Admins control the order; title breaks ties so the list is deterministic.
        stmt = stmt.order_by(Topic.sort_order, Topic.title)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get(self, topic_id: uuid.UUID) -> Topic | None:
        return await self.session.get(Topic, topic_id)

    async def get_by_slug(self, slug: str) -> Topic | None:
        result = await self.session.execute(select(Topic).where(Topic.slug == slug))
        return result.scalar_one_or_none()

    async def add(self, topic: Topic) -> Topic:
        self.session.add(topic)
        await self.session.flush()  # assign PK/defaults; commit handled by the session dependency
        return topic

    async def delete(self, topic: Topic) -> None:
        await self.session.delete(topic)

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(Topic)) or 0
