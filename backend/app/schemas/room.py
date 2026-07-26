"""Room request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ConversationMode, RoomKind


class RoomCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    mode: ConversationMode = ConversationMode.normal
    kind: RoomKind = RoomKind.group
    topic: str | None = Field(default=None, max_length=120)
    level: str | None = Field(default=None, max_length=40)
    # Optional; a 1-on-1 is always 2 seats, a group defaults to 4 (see service).
    capacity: int | None = Field(default=None, ge=2, le=20)
    # The creator becomes the room owner/host who can moderate it (PRD §8.3).
    owner_id: uuid.UUID | None = None


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    mode: ConversationMode
    kind: RoomKind
    topic: str | None
    level: str | None
    status: str
    capacity: int
    participant_count: int
    owner_id: uuid.UUID | None
    created_at: datetime
