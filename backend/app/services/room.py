"""Business logic for rooms and room membership."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password, verify_password
from app.models.enums import ConversationMode, RoomKind, UserRole
from app.models.participant import RoomParticipant
from app.models.room import Room
from app.models.user import User
from app.repositories.audit import AuditRepository
from app.repositories.participant import ParticipantRepository
from app.repositories.room import RoomRepository
from app.repositories.room_ban import RoomBanRepository
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
        bans: RoomBanRepository,
        audit: AuditRepository | None = None,
    ) -> None:
        self.rooms = rooms
        self.participants = participants
        self.users = users
        self.bans = bans
        # Only needed for admin deletions, which are privileged actions on
        # somebody else's content and belong in the audit log.
        self.audit = audit

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
        capacity = 2 if payload.kind is RoomKind.one_on_one else (payload.capacity or 4)
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
            # Store only a hash; a public room leaves this NULL.
            password_hash=hash_password(payload.password) if payload.password else None,
        )
        return await self.rooms.add(room)

    async def join_room(
        self,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
        display_name: str | None = None,
        password: str | None = None,
    ) -> Room:
        room = await self.get_room(room_id)

        # A member the owner kicked cannot rejoin the same room (PRD §8.3).
        # Bans used to be a process-local dict, so a deploy cleared them and
        # nothing could lift one (docs/11_Security.md Step 4). They now live in
        # `room_bans`, survive restarts, and expire.
        if await self.bans.is_banned(room_id, user_id):
            raise ForbiddenError("You were removed from this room", code="room_banned")

        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")

        # Joining is idempotent — a user already in the room just stays (and does
        # not need to re-enter the password).
        existing = await self.participants.get_active(room_id, user_id)
        if existing is not None:
            return room

        # Password-protected rooms require the correct password to join. The owner
        # (who set it) is exempt. The same error covers missing and wrong passwords.
        if (
            room.password_hash is not None
            and user_id != room.owner_id
            and (not password or not verify_password(password, room.password_hash))
        ):
            raise ForbiddenError(
                "This room requires the correct password to join.", code="room_password"
            )

        if room.participant_count >= room.capacity:
            raise ConflictError("Room is full", code="room_full")

        # No override → show the user's profile name (incognito passes an alias).
        name = (display_name or "").strip() or user.display_name
        await self.participants.add(
            RoomParticipant(room_id=room_id, user_id=user_id, display_name=name)
        )
        room.participant_count += 1
        return room

    async def delete_room(self, room_id: uuid.UUID, actor: User) -> int:
        """Delete a room. The owner may delete theirs; an admin may delete any.

        Returns how many people were still in it, so the caller can warn.

        This is a real delete, not a close: the room's messages, transcript,
        participants and bans go with it. Coach reports and AI usage survive with
        a NULL room, because they are the learner's own record of their practice
        and losing those to somebody else's tidy-up would be wrong.

        Raises:
            NotFoundError: no such room.
            ForbiddenError: the caller is neither the owner nor an admin.
        """
        room = await self.get_room(room_id)

        is_owner = room.owner_id is not None and room.owner_id == actor.id
        is_admin = actor.role == UserRole.admin
        if not is_owner and not is_admin:
            raise ForbiddenError("Only the room owner can delete this room")

        still_inside = room.participant_count

        # An admin removing somebody else's room is a privileged act on content
        # they do not own. The owner tidying up their own room is not.
        if is_admin and not is_owner and self.audit is not None:
            await self.audit.record(
                actor_id=actor.id,
                actor_name=actor.display_name,
                action="room.delete",
                target_type="room",
                target_id=room.id,
                target_name=room.title,
                detail=f"deleted a room with {still_inside} participant(s)",
            )

        await self.rooms.delete(room)
        return still_inside

    async def leave_room(self, room_id: uuid.UUID, user_id: uuid.UUID) -> Room:
        room = await self.get_room(room_id)
        participant = await self.participants.get_active(room_id, user_id)
        if participant is not None:
            participant.left_at = datetime.now(UTC)
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
                participant.left_at = datetime.now(UTC)
                room.participant_count = max(0, room.participant_count - 1)
            await self.bans.upsert(
                room_id,
                target_user_id,
                banned_by=owner_id,
                reason="Removed by the room owner",
                expires_at=moderation.default_expiry(settings.room_ban_hours),
            )
        return room
