"""WebSocket endpoint for live room conversations.

Clients connect to ``/ws/rooms/{room_id}?user_id=...&name=...``. Each inbound
``{"text": "..."}`` frame is persisted and then broadcast to everyone in the
room as ``{"type": "message", "message": {...}}``. Join/leave produce
``{"type": "presence", ...}`` frames so the UI can show who is around.
"""

import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.db.session import AsyncSessionLocal
from app.realtime.connection_manager import manager
from app.repositories.message import MessageRepository
from app.repositories.participant import ParticipantRepository
from app.repositories.room import RoomRepository
from app.repositories.user import UserRepository
from app.schemas.message import MessageRead
from app.services import moderation
from app.services.conversation import ConversationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(
    websocket: WebSocket,
    room_id: str,
    user_id: str = Query(...),
    name: str = Query(default="Guest"),
) -> None:
    try:
        room_uuid = uuid.UUID(room_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        await websocket.close(code=1008)  # policy violation: bad identifiers
        return

    # A kicked member cannot reconnect to the room's chat (PRD §8.3).
    if moderation.is_banned(room_id, user_id):
        await websocket.close(code=1008)
        return

    await manager.connect(room_id, websocket, user_id, name)
    # Hand the newcomer the current roster so they immediately see everyone who
    # joined earlier (not just people who join after them).
    await websocket.send_json({"type": "roster", "members": manager.roster(room_id)})
    await manager.broadcast(
        room_id, {"type": "presence", "event": "join", "name": name, "user_id": user_id}
    )

    try:
        while True:
            data = await websocket.receive_json()
            text = (data.get("text") or "").strip()
            if not text:
                continue

            async with AsyncSessionLocal() as session:
                service = ConversationService(
                    MessageRepository(session),
                    RoomRepository(session),
                    UserRepository(session),
                    ParticipantRepository(session),
                )
                try:
                    message = await service.post_message(room_uuid, user_uuid, text)
                    await session.commit()
                except Exception:  # noqa: BLE001 — report to sender, keep socket alive
                    await session.rollback()
                    await websocket.send_json(
                        {"type": "error", "message": "Could not send message"}
                    )
                    continue
                payload = MessageRead.model_validate(message).model_dump(mode="json")

            await manager.broadcast(room_id, {"type": "message", "message": payload})
    except WebSocketDisconnect:
        manager.disconnect(room_id, websocket)
        await manager.broadcast(
            room_id, {"type": "presence", "event": "leave", "name": name, "user_id": user_id}
        )
