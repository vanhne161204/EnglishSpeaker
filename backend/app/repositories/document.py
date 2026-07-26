"""Data-access for topic documents (Documentation Content)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, topic_id: uuid.UUID | None = None) -> Sequence[Document]:
        stmt = select(Document)
        if topic_id is not None:
            stmt = stmt.where(Document.topic_id == topic_id)
        stmt = stmt.order_by(Document.created_at)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get(self, document_id: uuid.UUID) -> Document | None:
        return await self.session.get(Document, document_id)

    async def add(self, document: Document) -> Document:
        self.session.add(document)
        await self.session.flush()
        return document

    async def delete(self, document: Document) -> None:
        await self.session.delete(document)

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(Document)) or 0
