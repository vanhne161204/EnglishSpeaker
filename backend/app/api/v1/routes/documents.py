"""Topic-document endpoints (Documentation Content, PRD §8.2).

Admins create/edit/delete documents; users (and the AI coach) read them, usually
filtered by topic. Writes require an admin (``require_admin``); reads are open.
"""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, status

from app.api.deps import get_document_service, require_admin
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentCreate, DocumentRead, DocumentUpdate
from app.services.document import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get(
    "",
    response_model=list[DocumentRead],
    summary="List documents (optionally filtered by topic)",
)
async def list_documents(
    topic_id: uuid.UUID | None = None,
    service: DocumentService = Depends(get_document_service),
) -> Sequence[Document]:
    return await service.list_documents(topic_id)


@router.post(
    "",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a learning document to a topic (admin)",
)
async def create_document(
    payload: DocumentCreate,
    service: DocumentService = Depends(get_document_service),
    _: User = Depends(require_admin),
) -> Document:
    return await service.create_document(payload)


@router.get("/{document_id}", response_model=DocumentRead, summary="Get a document")
async def get_document(
    document_id: uuid.UUID,
    service: DocumentService = Depends(get_document_service),
) -> Document:
    return await service.get_document(document_id)


@router.patch("/{document_id}", response_model=DocumentRead, summary="Edit a document (admin)")
async def update_document(
    document_id: uuid.UUID,
    payload: DocumentUpdate,
    service: DocumentService = Depends(get_document_service),
    _: User = Depends(require_admin),
) -> Document:
    return await service.update_document(document_id, payload)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document (admin)",
)
async def delete_document(
    document_id: uuid.UUID,
    service: DocumentService = Depends(get_document_service),
    _: User = Depends(require_admin),
) -> None:
    await service.delete_document(document_id)
