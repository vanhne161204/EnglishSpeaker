"""Document model — admin learning content for a topic (PRD §8.2).

Each document is a piece of trusted material (explanation, example, vocabulary,
common mistake, tip, or sample answer) attached to a topic. It powers a room's
"related documents" and is the source the AI coach can ground its help in (RAG).
"""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Validated against DocumentKind at the API layer; stored as a short string.
    kind: Mapped[str] = mapped_column(
        String(30), default="explanation", server_default="explanation", nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
