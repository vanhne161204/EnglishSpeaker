"""Topic request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TopicBase(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    level: str | None = Field(default=None, max_length=40)
    # Admin-authored questions for Warm-up (PRD §8.1). Empty unless the admin adds them.
    sample_questions: list[str] = Field(default_factory=list)


class TopicCreate(TopicBase):
    pass


class TopicUpdate(BaseModel):
    # Slug is the stable key, so it is not editable here. Other fields are optional.
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    level: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=20)
    sample_questions: list[str] | None = None


class TopicRead(TopicBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    created_at: datetime
