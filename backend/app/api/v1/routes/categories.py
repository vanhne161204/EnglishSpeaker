"""Category endpoints — topic grouping (PRD §8.1).

Reads are open; writes require an admin.
"""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, status

from app.api.deps import get_category_service, require_admin
from app.models.category import Category
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.services.category import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead], summary="List categories")
async def list_categories(
    service: CategoryService = Depends(get_category_service),
) -> Sequence[Category]:
    return await service.list_categories()


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category (admin)",
)
async def create_category(
    payload: CategoryCreate,
    service: CategoryService = Depends(get_category_service),
    _: User = Depends(require_admin),
) -> Category:
    return await service.create_category(payload)


@router.get("/{category_id}", response_model=CategoryRead, summary="Get a category")
async def get_category(
    category_id: uuid.UUID,
    service: CategoryService = Depends(get_category_service),
) -> Category:
    return await service.get_category(category_id)


@router.patch("/{category_id}", response_model=CategoryRead, summary="Edit a category (admin)")
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    service: CategoryService = Depends(get_category_service),
    _: User = Depends(require_admin),
) -> Category:
    return await service.update_category(category_id, payload)


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a category (admin)",
)
async def delete_category(
    category_id: uuid.UUID,
    service: CategoryService = Depends(get_category_service),
    _: User = Depends(require_admin),
) -> None:
    # Topics in this category are kept; they just lose their grouping.
    await service.delete_category(category_id)
