"""Schemas for the AI voice coach (PRD §8.12, docs/08_API.md)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VoiceCoachUsage(BaseModel):
    """Today's allowance. ``enabled`` is false when the server has no Gemini key."""

    enabled: bool
    daily_limit_seconds: int
    used_seconds: int
    remaining_seconds: int
    session_max_seconds: int
    resets_at: datetime


class VoiceSessionCreate(BaseModel):
    # None = the general warm-up: a mix of questions across topics.
    topic_id: uuid.UUID | None = None


class VoiceSessionStarted(BaseModel):
    id: uuid.UUID
    token: str = Field(
        description="One-use Gemini Live ephemeral token. Pass it as the SDK apiKey."
    )
    model: str = Field(description="The model the token is locked to. Connect with this one.")
    expires_at: datetime
    max_seconds: int
    remaining_seconds: int = Field(
        description="Seconds left today after this session's full limit is held."
    )
    topic_title: str | None
    questions: list[str]


class VoiceSessionEnded(BaseModel):
    id: uuid.UUID
    used_seconds: int
    remaining_seconds: int
