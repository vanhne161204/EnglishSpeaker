"""Room endpoints: listing, membership, and message history."""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, status

from app.api.deps import get_conversation_service, get_current_user, get_room_service
from app.models.enums import ConversationMode, RoomKind
from app.models.message import Message
from app.models.room import Room
from app.models.user import User
from app.realtime.connection_manager import manager
from app.schemas.message import MessageCreate, MessageRead
from app.schemas.moderation import ModerateRequest, ModerateResult
from app.schemas.participant import JoinRequest
from app.schemas.room import RoomCreate, RoomDeleted, RoomRead
from app.services.conversation import ConversationService
from app.services.room import RoomService

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomRead], summary="List open rooms (by mode and kind)")
async def list_rooms(
    mode: ConversationMode | None = None,
    kind: RoomKind | None = None,
    service: RoomService = Depends(get_room_service),
) -> Sequence[Room]:
    return await service.list_rooms(mode, kind)


@router.post(
    "",
    response_model=RoomRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a room",
)
async def create_room(
    payload: RoomCreate,
    user: User = Depends(get_current_user),
    service: RoomService = Depends(get_room_service),
) -> Room:
    # The creator owns the room. Taking `owner_id` from the body would let a
    # caller create a room owned by somebody else, then moderate it as them.
    payload = payload.model_copy(update={"owner_id": user.id})
    return await service.create_room(payload)


@router.get("/{room_id}", response_model=RoomRead, summary="Get a single room")
async def get_room(
    room_id: uuid.UUID,
    service: RoomService = Depends(get_room_service),
) -> Room:
    return await service.get_room(room_id)


@router.post("/{room_id}/join", response_model=RoomRead, summary="Join a room")
async def join_room(
    room_id: uuid.UUID,
    payload: JoinRequest,
    user: User = Depends(get_current_user),
    service: RoomService = Depends(get_room_service),
) -> Room:
    return await service.join_room(room_id, user.id, payload.display_name, payload.password)


@router.delete(
    "/{room_id}",
    response_model=RoomDeleted,
    summary="Delete a room (owner or admin)",
)
async def delete_room(
    room_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: RoomService = Depends(get_room_service),
) -> RoomDeleted:
    """Delete a room and everything said in it.

    Permitted for the room's owner, and for any admin. Both are checked against
    the database inside the service — the caller never says which they are.

    Anyone still connected is told over the socket, so they land back on the room
    list with an explanation instead of sitting in a page whose every request has
    started returning 404.
    """
    still_inside = await service.delete_room(room_id, user)

    await manager.broadcast(
        str(room_id),
        {"type": "room_closed", "reason": "The host closed this room."},
    )
    return RoomDeleted(id=room_id, participants_removed=still_inside)


@router.post("/{room_id}/leave", response_model=RoomRead, summary="Leave a room")
async def leave_room(
    room_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: RoomService = Depends(get_room_service),
) -> Room:
    return await service.leave_room(room_id, user.id)


@router.post(
    "/{room_id}/moderate",
    response_model=ModerateResult,
    summary="Room owner mutes, unmutes, or kicks a member (PRD §8.3)",
)
async def moderate_member(
    room_id: uuid.UUID,
    payload: ModerateRequest,
    user: User = Depends(get_current_user),
    service: RoomService = Depends(get_room_service),
) -> ModerateResult:
    # Ownership is checked against the TOKEN, never a body field. The service
    # raises 403 when the caller does not own this room.
    await service.moderate(room_id, user.id, payload.target_user_id, payload.action)
    # Deliver the command to the room over the live chat channel; each client acts
    # on it if it is the target (leave on kick, mute/unmute its own mic).
    await manager.broadcast(
        str(room_id),
        {
            "type": "moderation",
            "action": payload.action.value,
            "target": str(payload.target_user_id),
        },
    )
    return ModerateResult(ok=True, action=payload.action, target_user_id=payload.target_user_id)


@router.get(
    "/{room_id}/messages",
    response_model=list[MessageRead],
    summary="Get recent messages in a room",
)
async def list_messages(
    room_id: uuid.UUID,
    service: ConversationService = Depends(get_conversation_service),
) -> Sequence[Message]:
    return await service.list_messages(room_id)


@router.post(
    "/{room_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message (REST fallback for WebSocket)",
)
async def create_message(
    room_id: uuid.UUID,
    payload: MessageCreate,
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> Message:
    return await service.post_message(room_id, user.id, payload.text)
