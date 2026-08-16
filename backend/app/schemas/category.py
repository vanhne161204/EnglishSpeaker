"""Category request/response schemas (PRD §8.1)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=140)
    description: str | None = None
    icon_url: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    # Slug is the stable key, so it is not editable here. Everything else is optional.
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    icon_url: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
