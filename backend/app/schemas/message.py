"""Chat message request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    user_id: uuid.UUID
    text: str = Field(min_length=1, max_length=2000)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    user_id: uuid.UUID
    sender_name: str
    text: str
    created_at: datetime
