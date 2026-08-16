"""ORM models.

Importing every model here ensures they are registered on ``Base.metadata``
(needed by Alembic autogenerate and by dev-mode ``create_all``).
"""

from app.models.category import Category
from app.models.doc import AnswerTemplate, Doc, DocItem, DocSection, Question
from app.models.message import Message
from app.models.participant import RoomParticipant
from app.models.room import Room
from app.models.sentence_note import SentenceNote
from app.models.topic import Topic
from app.models.user import User

__all__ = [
    "AnswerTemplate",
    "Category",
    "Doc",
    "DocItem",
    "DocSection",
    "Message",
    "Question",
    "Room",
    "RoomParticipant",
    "SentenceNote",
    "Topic",
    "User",
]
