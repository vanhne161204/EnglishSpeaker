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

from app.api.deps import authenticate_socket
from app.realtime.voice_manager import voice_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])

# Signaling frames that are forwarded to a single target peer (must carry "to").
_RELAY_TYPES = {"offer", "answer", "ice-candidate"}


@router.websocket("/ws/voice/{room_id}")
async def voice_socket(
    websocket: WebSocket,
    room_id: str,
    token: str = Query(..., description="Session JWT — identity comes from this, only this."),
    name: str = Query(default=""),
) -> None:
    try:
        uuid.UUID(room_id)
    except ValueError:
        await websocket.close(code=1008)  # policy violation: bad room id
        return

    identity = await authenticate_socket(token)
    if identity is None:
        await websocket.close(code=1008)
        return
    user_uuid, profile_name = identity
    user_id = str(user_uuid)
    # An incognito room supplies an alias; it is a display label only and can
    # never change who the server thinks you are.
    name = name.strip()[:80] or profile_name

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
