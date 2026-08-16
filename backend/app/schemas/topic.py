"""Topic request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TopicBase(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    level: str | None = Field(default=None, max_length=40)
    category_id: uuid.UUID | None = None
    cover_image_url: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class TopicCreate(TopicBase):
    pass


class TopicUpdate(BaseModel):
    # Slug is the stable key, so it is not editable here. Other fields are optional.
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    level: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=20)
    category_id: uuid.UUID | None = None
    cover_image_url: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class TopicRead(TopicBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    created_at: datetime
