"""User (lightweight profile) endpoints."""

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import get_subscription_service, get_user_service
from app.models.user import User
from app.schemas.subscription import SubscriptionRead, SubscriptionUpdate
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.subscription import SubscriptionService
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lightweight profile",
)
async def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.create_user(payload)


@router.get("/{user_id}", response_model=UserRead, summary="Get a profile")
async def get_user(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.get_user(user_id)


@router.patch("/{user_id}", response_model=UserRead, summary="Update a profile")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.update_user(user_id, payload)


@router.get(
    "/{user_id}/subscription",
    response_model=SubscriptionRead,
    summary="Get the user's plan and limits",
)
async def get_subscription(
    user_id: uuid.UUID,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionRead:
    return await service.get_subscription(user_id)


@router.put(
    "/{user_id}/subscription",
    response_model=SubscriptionRead,
    summary="Upgrade or cancel the user's plan",
)
async def set_subscription(
    user_id: uuid.UUID,
    payload: SubscriptionUpdate,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionRead:
    return await service.set_plan(user_id, payload.plan)
