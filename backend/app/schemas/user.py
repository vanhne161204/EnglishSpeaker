"""User (lightweight profile) request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole


class UserCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    level: str | None = Field(default=None, max_length=40)
    interests: str | None = Field(default=None, max_length=300)


class UserUpdate(BaseModel):
    # All optional — only provided fields change (PATCH semantics).
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    level: str | None = Field(default=None, max_length=40)
    interests: str | None = Field(default=None, max_length=300)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    username: str | None
    role: UserRole
    phone: str | None
    level: str | None
    interests: str | None
    plan: str
    created_at: datetime
