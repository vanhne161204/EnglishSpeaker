"""Sentence-note request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class NoteBase(BaseModel):
    original_text: str | None = None
    improved_text: str | None = None
    source: str = "self"
    topic: str | None = None

    @model_validator(mode="after")
    def _require_some_text(self) -> "NoteBase":
        if not self.original_text and not self.improved_text:
            raise ValueError("Provide original_text or improved_text")
        return self


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    # All optional — only provided fields change (PATCH semantics).
    original_text: str | None = None
    improved_text: str | None = None
    source: str | None = None
    topic: str | None = None


class NoteRead(NoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
