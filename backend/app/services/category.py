"""Business logic for topic categories (PRD §8.1)."""

import uuid
from collections.abc import Sequence

from app.core.exceptions import ConflictError, NotFoundError
from app.models.category import Category
from app.repositories.category import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:
    def __init__(self, repository: CategoryRepository) -> None:
        self.repository = repository

    async def list_categories(self) -> Sequence[Category]:
        return await self.repository.list()

    async def get_category(self, category_id: uuid.UUID) -> Category:
        category = await self.repository.get(category_id)
        if category is None:
            raise NotFoundError("Category not found")
        return category

    async def create_category(self, payload: CategoryCreate) -> Category:
        if await self.repository.get_by_slug(payload.slug):
            raise ConflictError(f"Category with slug '{payload.slug}' already exists")
        return await self.repository.add(Category(**payload.model_dump()))

    async def update_category(self, category_id: uuid.UUID, payload: CategoryUpdate) -> Category:
        category = await self.get_category(category_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(category, field, value)
        return category

    async def delete_category(self, category_id: uuid.UUID) -> None:
        # Topics keep working — their ``category_id`` is set to NULL by the FK.
        category = await self.get_category(category_id)
        await self.repository.delete(category)
