"""Business logic for rooms and room membership."""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.enums import ConversationMode, RoomKind
from app.models.participant import RoomParticipant
from app.models.room import Room
from app.repositories.participant import ParticipantRepository
from app.repositories.room import RoomRepository
from app.repositories.user import UserRepository
from app.schemas.moderation import ModerationAction
from app.schemas.room import RoomCreate
from app.services import moderation


class RoomService:
    def __init__(
        self,
        rooms: RoomRepository,
        participants: ParticipantRepository,
        users: UserRepository,
    ) -> None:
        self.rooms = rooms
        self.participants = participants
        self.users = users

    async def list_rooms(
        self,
        mode: ConversationMode | None = None,
        kind: RoomKind | None = None,
    ) -> Sequence[Room]:
        return await self.rooms.list(mode, kind)

    async def get_room(self, room_id: uuid.UUID) -> Room:
        room = await self.rooms.get(room_id)
        if room is None:
            raise NotFoundError("Room not found")
        return room

    async def create_room(self, payload: RoomCreate) -> Room:
        # A 1-on-1 always seats two; a group defaults to four when unspecified.
        if payload.kind is RoomKind.one_on_one:
            capacity = 2
        else:
            capacity = payload.capacity or 4
        room = Room(
            title=payload.title.strip(),
            mode=payload.mode.value,
            kind=payload.kind.value,
            topic=payload.topic,
            level=payload.level,
            status="open",
            capacity=capacity,
            participant_count=0,
            owner_id=payload.owner_id,
        )
        return await self.rooms.add(room)

    async def join_room(
        self,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
        display_name: str | None = None,
    ) -> Room:
        room = await self.get_room(room_id)

        # A member the owner kicked cannot rejoin the same room (PRD §8.3).
        if moderation.is_banned(room_id, user_id):
            raise ForbiddenError("You were removed from this room", code="room_banned")

        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")

        # Joining is idempotent — a user already in the room just stays.
        existing = await self.participants.get_active(room_id, user_id)
        if existing is not None:
            return room

        if room.participant_count >= room.capacity:
            raise ConflictError("Room is full", code="room_full")

        # No override → show the user's profile name (incognito passes an alias).
        name = (display_name or "").strip() or user.display_name
        await self.participants.add(
            RoomParticipant(room_id=room_id, user_id=user_id, display_name=name)
        )
        room.participant_count += 1
        return room

    async def leave_room(self, room_id: uuid.UUID, user_id: uuid.UUID) -> Room:
        room = await self.get_room(room_id)
        participant = await self.participants.get_active(room_id, user_id)
        if participant is not None:
            participant.left_at = datetime.now(timezone.utc)
            room.participant_count = max(0, room.participant_count - 1)
        return room

    async def moderate(
        self,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
        target_user_id: uuid.UUID,
        action: ModerationAction,
    ) -> Room:
        """Apply an owner moderation command (PRD §8.3 owner controls).

        Only the room's owner may moderate, and never themselves. Mute/unmute have
        no persistent effect (they are delivered as a realtime signal the target's
        client follows); kick removes the participant and bans them from rejoining.

        Raises:
            NotFoundError: the room does not exist.
            ForbiddenError: the caller is not the owner, or targets themselves.
        """
        room = await self.get_room(room_id)
        if room.owner_id is None or room.owner_id != owner_id:
            raise ForbiddenError("Only the room owner can moderate members")
        if target_user_id == owner_id:
            raise ForbiddenError("The owner cannot moderate themselves")

        if action is ModerationAction.kick:
            participant = await self.participants.get_active(room_id, target_user_id)
            if participant is not None:
                participant.left_at = datetime.now(timezone.utc)
                room.participant_count = max(0, room.participant_count - 1)
            moderation.ban(room_id, target_user_id)
        return room
