"""Business logic for users (lightweight profiles)."""

import uuid

from app.core.exceptions import NotFoundError
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self.repository.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def create_user(self, payload: UserCreate) -> User:
        return await self.repository.add(User(**payload.model_dump()))

    async def update_user(self, user_id: uuid.UUID, payload: UserUpdate) -> User:
        user = await self.get_user(user_id)
        # Only overwrite fields the client actually sent (PATCH semantics).
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        return user
