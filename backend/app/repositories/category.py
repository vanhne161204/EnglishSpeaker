"""Data-access for topic categories (PRD §8.1)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> Sequence[Category]:
        stmt = select(Category).order_by(Category.sort_order, Category.name)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get(self, category_id: uuid.UUID) -> Category | None:
        return await self.session.get(Category, category_id)

    async def get_by_slug(self, slug: str) -> Category | None:
        result = await self.session.execute(select(Category).where(Category.slug == slug))
        return result.scalar_one_or_none()

    async def add(self, category: Category) -> Category:
        self.session.add(category)
        await self.session.flush()  # assign PK/defaults; the session dependency commits
        return category

    async def delete(self, category: Category) -> None:
        await self.session.delete(category)

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(Category)) or 0
