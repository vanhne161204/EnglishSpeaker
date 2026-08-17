"""Sentence-note request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NoteBase(BaseModel):
    original_text: str | None = None
    improved_text: str | None = None
    # Translation pair saved from the in-room translator (PRD §8.10). The language
    # codes let the UI label each side instead of guessing which is which.
    translated_text: str | None = None
    source_lang: str | None = Field(default=None, max_length=10)
    target_lang: str | None = Field(default=None, max_length=10)
    source: str = "self"
    topic: str | None = None

    @model_validator(mode="after")
    def _require_some_text(self) -> "NoteBase":
        if not self.original_text and not self.improved_text and not self.translated_text:
            raise ValueError("Provide original_text, improved_text, or translated_text")
        return self


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    # All optional — only provided fields change (PATCH semantics).
    original_text: str | None = None
    improved_text: str | None = None
    translated_text: str | None = None
    source_lang: str | None = Field(default=None, max_length=10)
    target_lang: str | None = Field(default=None, max_length=10)
    source: str | None = None
    topic: str | None = None


class NoteRead(NoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
