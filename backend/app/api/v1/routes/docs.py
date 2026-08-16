"""Topic documentation endpoints (PRD §8.2).

Reads return the whole tree in one call, because the UI renders a doc as one
page. Writes are per-node so an admin edit touches only what changed. Reads are
open; every write requires an admin.

Path layout — the fixed segment always comes before the id, so a 3-segment path
like ``/docs/sections/{id}`` never collides with ``/docs/{doc_id}``:

    /docs                              list, create
    /docs/{doc_id}                     read (full tree), edit, delete
    /docs/{doc_id}/sections            add a section
    /docs/sections/{section_id}        edit, delete a section
    /docs/sections/{section_id}/items  add a vocabulary/phrase item
    /docs/items/{item_id}              edit, delete an item
"""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, status

from app.api.deps import get_doc_service, require_admin
from app.models.doc import Doc, DocItem, DocSection
from app.models.user import User
from app.schemas.doc import (
    DocCreate,
    DocItemCreate,
    DocItemRead,
    DocItemUpdate,
    DocRead,
    DocSectionCreate,
    DocSectionRead,
    DocSectionUpdate,
    DocSummary,
    DocUpdate,
)
from app.services.doc import DocService

router = APIRouter(prefix="/docs", tags=["docs"])


# --- Docs -------------------------------------------------------------------


@router.get(
    "",
    response_model=list[DocSummary],
    summary="List docs (optionally filtered by topic)",
)
async def list_docs(
    topic_id: uuid.UUID | None = None,
    service: DocService = Depends(get_doc_service),
) -> Sequence[Doc]:
    return await service.list_docs(topic_id)


@router.post(
    "",
    response_model=DocSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Start a topic's documentation (admin)",
)
async def create_doc(
    payload: DocCreate,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> Doc:
    return await service.create_doc(payload)


@router.get("/{doc_id}", response_model=DocRead, summary="Get a doc with its full tree")
async def get_doc(
    doc_id: uuid.UUID,
    service: DocService = Depends(get_doc_service),
) -> Doc:
    return await service.get_doc(doc_id)


@router.patch("/{doc_id}", response_model=DocSummary, summary="Edit a doc (admin)")
async def update_doc(
    doc_id: uuid.UUID,
    payload: DocUpdate,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> Doc:
    return await service.update_doc(doc_id, payload)


@router.delete(
    "/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a doc and everything in it (admin)",
)
async def delete_doc(
    doc_id: uuid.UUID,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> None:
    await service.delete_doc(doc_id)


# --- Sections ---------------------------------------------------------------


@router.post(
    "/{doc_id}/sections",
    response_model=DocSectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a section to a doc (admin)",
)
async def create_section(
    doc_id: uuid.UUID,
    payload: DocSectionCreate,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> DocSection:
    return await service.create_section(doc_id, payload)


@router.patch(
    "/sections/{section_id}",
    response_model=DocSectionRead,
    summary="Edit a section (admin)",
)
async def update_section(
    section_id: uuid.UUID,
    payload: DocSectionUpdate,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> DocSection:
    return await service.update_section(section_id, payload)


@router.delete(
    "/sections/{section_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a section and its contents (admin)",
)
async def delete_section(
    section_id: uuid.UUID,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> None:
    await service.delete_section(section_id)


# --- Items (vocabulary / phrases) -------------------------------------------


@router.post(
    "/sections/{section_id}/items",
    response_model=DocItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a word or phrase to a section (admin)",
)
async def create_item(
    section_id: uuid.UUID,
    payload: DocItemCreate,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> DocItem:
    # 400 if the section is not a 'vocabulary' or 'phrases' section.
    return await service.create_item(section_id, payload)


@router.patch("/items/{item_id}", response_model=DocItemRead, summary="Edit an item (admin)")
async def update_item(
    item_id: uuid.UUID,
    payload: DocItemUpdate,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> DocItem:
    return await service.update_item(item_id, payload)


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an item (admin)",
)
async def delete_item(
    item_id: uuid.UUID,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> None:
    await service.delete_item(item_id)
