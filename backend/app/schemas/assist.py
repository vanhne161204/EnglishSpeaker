"""AI conversation-help schemas (in-room coach, PRD §8.8, docs/10_AI_Design §10.2)."""

import uuid
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class AssistKind(StrEnum):
    """What kind of help the user is asking for."""

    # Rewrite the user's own sentence to be more natural and correct.
    improve = "improve"
    # Suggest something the user could say next, given the conversation.
    reply = "reply"
    # "I'm stuck" modes (docs/10_AI_Design.md §10.2). `answer` and `ask` read the
    # room's recent speech; `say_this` turns the learner's own idea (often
    # Vietnamese) into English — the most common block is not "no idea", it is
    # "I know what I mean but cannot build the sentence".
    answer = "answer"
    ask = "ask"
    say_this = "say_this"


#: Kinds that need the learner's own text rather than the room's conversation.
_NEEDS_TEXT = {AssistKind.improve, AssistKind.say_this}


class AssistRequest(BaseModel):
    kind: AssistKind = AssistKind.improve
    # The user's draft sentence (required for "improve" and "say_this").
    text: str = Field(default="", max_length=2000)
    # Recent conversation context (used for "reply", "answer", "ask").
    context: str | None = Field(default=None, max_length=2000)
    # Optional topic to ground suggestions in its admin documents (RAG, §8.2/§8.8).
    topic_id: uuid.UUID | None = None
    # How hard the suggestion may be. Accepts a CEFR code ("A2", "B1") or the
    # word a room uses ("beginner", "intermediate", "advanced") — `prompts.py`
    # normalises both. Wide enough for the room model's String(40) values;
    # capping at 4 would 422 every request from a room with a worded level.
    level: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _require_text_where_it_is_the_input(self) -> "AssistRequest":
        if self.kind in _NEEDS_TEXT and not self.text.strip():
            raise ValueError(f"text is required for kind={self.kind.value}")
        return self


class AssistResult(BaseModel):
    # Kept as the primary field so existing clients keep working while the
    # frontend migrates to `suggestions` (docs/10_AI_Design.md §10.2).
    suggestion: str
    kind: AssistKind
    # Which engine answered: "openai", "anthropic", or "stub" in demo mode.
    provider: str
    # True when a fallback answered instead of the first-choice model, or when
    # the AI was unavailable and this is the demo stub. Lets the UI soften.
    degraded: bool = False
