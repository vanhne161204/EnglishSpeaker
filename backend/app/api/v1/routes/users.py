"""Profile and subscription endpoints.

Every route acts on the **authenticated caller**, never on an id from the URL.
Taking the id from the path meant anyone could edit anyone's profile — and, via
the subscription route, grant themselves premium or downgrade somebody else
(docs/11_Security.md §11.4).

There is no `POST /users`. Accounts are created by `POST /auth/register`, which
requires a password; a second, password-free creation path would be a way in.
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_subscription_service, get_user_service
from app.models.user import User
from app.schemas.subscription import SubscriptionRead, SubscriptionUpdate
from app.schemas.user import UserRead, UserUpdate
from app.services.subscription import SubscriptionService
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead, summary="My profile")
async def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserRead, summary="Update my profile")
async def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.update_user(user.id, payload)


@router.get(
    "/me/subscription",
    response_model=SubscriptionRead,
    summary="My plan and limits",
)
async def get_my_subscription(
    user: User = Depends(get_current_user),
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionRead:
    return await service.get_subscription(user.id)


@router.put(
    "/me/subscription",
    response_model=SubscriptionRead,
    summary="Change my plan",
)
async def set_my_subscription(
    payload: SubscriptionUpdate,
    user: User = Depends(get_current_user),
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionRead:
    # TODO(payments): this currently trusts the caller to choose their own plan,
    # which is fine only while nothing is charged for. Once billing exists, the
    # plan must be set by the payment webhook, never by the client.
    return await service.set_plan(user.id, payload.plan)
