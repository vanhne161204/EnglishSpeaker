"""Topic documentation models — the learner's scaffolding (PRD §8.2).

One topic has one doc. A doc is an ordered list of sections, and a section's type
decides where its content lives:

    Doc
     └── DocSection (vocabulary | phrases | questions | tips | text)
          ├── DocItem          — vocabulary / phrases sections
          └── Question         — questions sections
               └── AnswerTemplate

``tips`` and ``text`` sections carry free-form prose in ``DocSection.body`` and
have no children.

Every relationship uses ``lazy="selectin"``, so reading a doc loads the whole tree
in a fixed number of queries. That matters twice over: it avoids N+1 queries, and
it keeps the tree usable under asyncio, where a lazy load after the fact would
raise ``MissingGreenlet``. Deletes cascade down the tree in both the ORM
(``delete-orphan``) and the database (``ondelete="CASCADE"``).
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Doc(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "docs"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True, unique=True, nullable=False
    )
    # Optional; the API falls back to the topic's title when this is empty.
    title: Mapped[str | None] = mapped_column(String(200), default=None)
    intro: Mapped[str | None] = mapped_column(Text, default=None)
    # Optional override of the topic's level (same vocabulary: beginner…advanced).
    level: Mapped[str | None] = mapped_column(String(40), default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")

    sections: Mapped[list["DocSection"]] = relationship(
        back_populates="doc",
        cascade="all, delete-orphan",
        order_by="(DocSection.sort_order, DocSection.created_at)",
        lazy="selectin",
    )


class DocSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "doc_sections"

    doc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Validated against DocSectionType at the API layer; stored as a short string
    # so the same schema works on SQLite (dev) and Postgres (prod).
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), default=None)
    # Used by 'tips' and 'text' sections; ignored by the item/question types.
    body: Mapped[str | None] = mapped_column(Text, default=None)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    doc: Mapped["Doc"] = relationship(back_populates="sections")
    items: Mapped[list["DocItem"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="(DocItem.sort_order, DocItem.created_at)",
        lazy="selectin",
    )
    questions: Mapped[list["Question"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="(Question.sort_order, Question.created_at)",
        lazy="selectin",
    )


class DocItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One word or phrase. Vocabulary and phrases share this shape (PRD §8.2)."""

    __tablename__ = "doc_items"

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doc_sections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    term: Mapped[str] = mapped_column(Text, nullable=False)
    phonetic: Mapped[str | None] = mapped_column(String(200), default=None)
    meaning: Mapped[str | None] = mapped_column(Text, default=None)
    translation: Mapped[str | None] = mapped_column(Text, default=None)
    example: Mapped[str | None] = mapped_column(Text, default=None)
    audio_url: Mapped[str | None] = mapped_column(String(500), default=None)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    section: Mapped["DocSection"] = relationship(back_populates="items")


class Question(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A conversation question. Drives Warm-up Practice (PRD §8.12)."""

    __tablename__ = "questions"

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doc_sections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    translation: Mapped[str | None] = mapped_column(Text, default=None)
    audio_url: Mapped[str | None] = mapped_column(String(500), default=None)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    section: Mapped["DocSection"] = relationship(back_populates="questions")
    answer_templates: Mapped[list["AnswerTemplate"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="(AnswerTemplate.sort_order, AnswerTemplate.created_at)",
        lazy="selectin",
    )


class AnswerTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A fill-in-the-blank answer a learner can lean on (PRD §8.2).

    ``template`` is the shape ("My favourite food is ___."), ``example`` is the
    same sentence filled in ("My favourite food is pizza.").
    """

    __tablename__ = "answer_templates"

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    template: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str | None] = mapped_column(Text, default=None)
    translation: Mapped[str | None] = mapped_column(Text, default=None)
    audio_url: Mapped[str | None] = mapped_column(String(500), default=None)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    question: Mapped["Question"] = relationship(back_populates="answer_templates")
