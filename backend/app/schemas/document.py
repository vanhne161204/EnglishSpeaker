"""Topic-document (Documentation Content) request/response schemas (PRD §8.2)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DocumentKind


class DocumentCreate(BaseModel):
    topic_id: uuid.UUID
    kind: DocumentKind = DocumentKind.explanation
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class DocumentUpdate(BaseModel):
    # All optional — only provided fields are changed (PATCH semantics).
    kind: DocumentKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic_id: uuid.UUID
    kind: DocumentKind
    title: str
    content: str
    created_at: datetime
