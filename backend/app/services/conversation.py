"""Business logic for chat messages within a room.

Shared by the REST endpoints (history + send fallback) and the WebSocket handler
so a message is persisted the same way regardless of transport.
"""

import uuid
from collections.abc import Sequence

from app.core.exceptions import NotFoundError
from app.models.message import Message
from app.repositories.message import MessageRepository
from app.repositories.participant import ParticipantRepository
from app.repositories.room import RoomRepository
from app.repositories.user import UserRepository


class ConversationService:
    def __init__(
        self,
        messages: MessageRepository,
        rooms: RoomRepository,
        users: UserRepository,
        participants: ParticipantRepository,
    ) -> None:
        self.messages = messages
        self.rooms = rooms
        self.users = users
        self.participants = participants

    async def list_messages(self, room_id: uuid.UUID, limit: int = 100) -> Sequence[Message]:
        return await self.messages.list_for_room(room_id, limit)

    async def post_message(
        self, room_id: uuid.UUID, user_id: uuid.UUID, text: str
    ) -> Message:
        text = text.strip()
        if not text:
            raise ValueError("Message text cannot be empty")

        room = await self.rooms.get(room_id)
        if room is None:
            raise NotFoundError("Room not found")
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")

        # Prefer the in-room alias so incognito rooms never leak the real name.
        participant = await self.participants.get_active(room_id, user_id)
        sender_name = participant.display_name if participant else user.display_name

        return await self.messages.add(
            Message(
                room_id=room_id,
                user_id=user_id,
                sender_name=sender_name,
                text=text,
            )
        )
