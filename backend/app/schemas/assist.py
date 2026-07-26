"""AI conversation-help schemas (in-room coach, PRD §8.8)."""

import uuid
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class AssistKind(StrEnum):
    """What kind of help the user is asking for."""

    # Rewrite the user's own sentence to be more natural and correct.
    improve = "improve"
    # Suggest something the user could say next, given the conversation.
    reply = "reply"


class AssistRequest(BaseModel):
    kind: AssistKind = AssistKind.improve
    # The user's draft sentence (required for "improve").
    text: str = Field(default="", max_length=2000)
    # Recent conversation context (used for "reply").
    context: str | None = Field(default=None, max_length=2000)
    # Optional topic to ground suggestions in its admin documents (RAG, §8.2/§8.8).
    topic_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _require_text_to_improve(self) -> "AssistRequest":
        if self.kind is AssistKind.improve and not self.text.strip():
            raise ValueError("text is required to improve a sentence")
        return self


class AssistResult(BaseModel):
    suggestion: str
    kind: AssistKind
    # "claude" when powered by the Claude API, "stub" in zero-config demo mode.
    provider: str
