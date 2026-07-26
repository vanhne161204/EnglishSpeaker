"""Matchmaking request schema (PRD §8.4, §8.5).

The result of a match is a room to join, so endpoints return ``RoomRead``.
"""

from pydantic import BaseModel, Field

from app.models.enums import ConversationMode


class MatchRequest(BaseModel):
    mode: ConversationMode = ConversationMode.normal
    topic: str | None = Field(default=None, max_length=120)
    level: str | None = Field(default=None, max_length=40)
    # A soft preference (PRD §8.6). When no topic room is found we also try to
    # match the user's interest against an open room's topic before giving up.
    interest: str | None = Field(default=None, max_length=120)
