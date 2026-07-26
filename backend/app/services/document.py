"""Business logic for topic documents (Documentation Content, PRD §8.2)."""

import uuid
from collections.abc import Sequence

from app.core.exceptions import NotFoundError
from app.models.document import Document
from app.repositories.document import DocumentRepository
from app.repositories.topic import TopicRepository
from app.schemas.document import DocumentCreate, DocumentUpdate


class DocumentService:
    def __init__(self, documents: DocumentRepository, topics: TopicRepository) -> None:
        self.documents = documents
        self.topics = topics

    async def list_documents(self, topic_id: uuid.UUID | None = None) -> Sequence[Document]:
        return await self.documents.list(topic_id)

    async def get_document(self, document_id: uuid.UUID) -> Document:
        document = await self.documents.get(document_id)
        if document is None:
            raise NotFoundError("Document not found")
        return document

    async def create_document(self, payload: DocumentCreate) -> Document:
        # Validate the link explicitly (SQLite doesn't enforce FKs by default).
        if await self.topics.get(payload.topic_id) is None:
            raise NotFoundError("Topic not found")
        return await self.documents.add(Document(**payload.model_dump()))

    async def update_document(self, document_id: uuid.UUID, payload: DocumentUpdate) -> Document:
        document = await self.get_document(document_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(document, field, value)
        return document

    async def delete_document(self, document_id: uuid.UUID) -> None:
        document = await self.get_document(document_id)
        await self.documents.delete(document)
