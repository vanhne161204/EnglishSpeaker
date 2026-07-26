"""WebRTC voice signaling endpoint for a room.

Clients connect to ``/ws/voice/{room_id}?user_id=...&name=...``. The server relays
signaling only (no audio): it tells a newcomer who is already present, notifies the
others that a peer joined/left, and forwards targeted ``offer`` / ``answer`` /
``ice-candidate`` frames between peers.

Mesh negotiation convention (avoids offer "glare"):
- On joining you receive ``{"type": "peers", "peers": [...]}`` and you create an
  offer to each of those existing peers.
- Existing peers receive ``{"type": "peer-joined", ...}`` and simply wait for the
  newcomer's offer, then answer.
"""

import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.realtime.voice_manager import voice_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])

# Signaling frames that are forwarded to a single target peer (must carry "to").
_RELAY_TYPES = {"offer", "answer", "ice-candidate"}


@router.websocket("/ws/voice/{room_id}")
async def voice_socket(
    websocket: WebSocket,
    room_id: str,
    user_id: str = Query(...),
    name: str = Query(default="Guest"),
) -> None:
    try:
        uuid.UUID(room_id)
        uuid.UUID(user_id)
    except ValueError:
        await websocket.close(code=1008)  # policy violation: bad identifiers
        return

    await websocket.accept()

    # Snapshot who is already here before registering, then announce ourselves.
    existing = voice_manager.others(room_id, user_id)
    voice_manager.add(room_id, user_id, name, websocket)
    await websocket.send_json({"type": "peers", "peers": existing})
    await voice_manager.broadcast(
        room_id,
        {"type": "peer-joined", "peer": {"id": user_id, "name": name}},
        exclude=user_id,
    )

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            target = message.get("to")
            if msg_type in _RELAY_TYPES and target:
                await voice_manager.send_to(
                    room_id,
                    target,
                    {"type": msg_type, "from": user_id, "data": message.get("data")},
                )
    except WebSocketDisconnect:
        voice_manager.remove(room_id, user_id)
        await voice_manager.broadcast(
            room_id, {"type": "peer-left", "peer": {"id": user_id}}, exclude=user_id
        )
