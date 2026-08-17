"""Topic documentation request/response schemas (PRD §8.2).

Reads are nested — one `GET` returns a doc with its sections, items, questions,
and answer templates — because the UI always renders the whole page at once.
Writes are per-node so an admin edit touches only the row it changed.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ContentStatus, DocSectionType

# --- Answer templates -------------------------------------------------------


class AnswerTemplateBase(BaseModel):
    template: str = Field(min_length=1)
    example: str | None = None
    translation: str | None = None
    audio_url: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class AnswerTemplateCreate(AnswerTemplateBase):
    pass


class AnswerTemplateUpdate(BaseModel):
    template: str | None = Field(default=None, min_length=1)
    example: str | None = None
    translation: str | None = None
    audio_url: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class AnswerTemplateRead(AnswerTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_id: uuid.UUID


# --- Questions --------------------------------------------------------------


class QuestionBase(BaseModel):
    text: str = Field(min_length=1)
    translation: str | None = None
    audio_url: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class QuestionCreate(QuestionBase):
    section_id: uuid.UUID


class QuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    translation: str | None = None
    audio_url: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class QuestionRead(QuestionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_id: uuid.UUID
    answer_templates: list[AnswerTemplateRead] = Field(default_factory=list)


class TopicQuestionRead(QuestionRead):
    """A question flattened with the topic it belongs to.

    Warm-up Practice (PRD §8.12) needs questions across many topics at once, so it
    reads this flat shape instead of walking each topic's doc tree.
    """

    topic_id: uuid.UUID
    topic_title: str


# --- Simple question-and-answer editing (PRD §8.1) --------------------------
#
# Authoring a question through the tree means four calls: create the doc, add a
# `questions` section, add the question, add its answer template. Admins write
# plain question-and-answer pairs, so these schemas back a single call that does
# all four steps. The tree is still the storage; this is just a flatter door.


class QAPair(BaseModel):
    """One question with its sample answer, as an admin types it."""

    text: str = Field(min_length=1)
    # Optional so an admin can save a question before they've written its answer.
    # A blank answer stores no answer template at all.
    answer: str | None = None


class QAPairRead(QAPair):
    id: uuid.UUID
    sort_order: int


class QASet(BaseModel):
    """The complete question list for a topic — saving replaces what was there."""

    items: list[QAPair] = Field(default_factory=list, max_length=50)


# --- Doc items (vocabulary / phrases) ---------------------------------------


class DocItemBase(BaseModel):
    term: str = Field(min_length=1)
    phonetic: str | None = Field(default=None, max_length=200)
    meaning: str | None = None
    translation: str | None = None
    example: str | None = None
    audio_url: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class DocItemCreate(DocItemBase):
    pass


class DocItemUpdate(BaseModel):
    term: str | None = Field(default=None, min_length=1)
    phonetic: str | None = Field(default=None, max_length=200)
    meaning: str | None = None
    translation: str | None = None
    example: str | None = None
    audio_url: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class DocItemRead(DocItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_id: uuid.UUID


# --- Sections ---------------------------------------------------------------


class DocSectionBase(BaseModel):
    type: DocSectionType
    title: str | None = Field(default=None, max_length=200)
    body: str | None = None
    sort_order: int = 0


class DocSectionCreate(DocSectionBase):
    pass


class DocSectionUpdate(BaseModel):
    # ``type`` is intentionally not editable: switching a section from
    # ``vocabulary`` to ``questions`` would orphan its children. Delete and
    # recreate the section instead.
    title: str | None = Field(default=None, max_length=200)
    body: str | None = None
    sort_order: int | None = None


class DocSectionRead(DocSectionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_id: uuid.UUID
    items: list[DocItemRead] = Field(default_factory=list)
    questions: list[QuestionRead] = Field(default_factory=list)


# --- Docs -------------------------------------------------------------------


class DocBase(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    intro: str | None = None
    level: str | None = Field(default=None, max_length=40)


class DocCreate(DocBase):
    topic_id: uuid.UUID
    status: ContentStatus = ContentStatus.draft


class DocUpdate(DocBase):
    status: ContentStatus | None = None


class DocSummary(DocBase):
    """A doc without its tree — used for lists and for write responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic_id: uuid.UUID
    status: ContentStatus
    created_at: datetime
    updated_at: datetime


class DocRead(DocSummary):
    sections: list[DocSectionRead] = Field(default_factory=list)
