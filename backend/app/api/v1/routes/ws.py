"""WebSocket endpoint for live room conversations and transcripts.

Clients connect to ``/ws/rooms/{room_id}?user_id=...&name=...``.

**Inbound frames**

* ``{"text": "..."}`` — a chat message. Persisted and broadcast.
  (No ``type`` field: this is the original contract and older clients still send
  exactly this. It must keep working.)
* ``{"type": "transcript", "text": "...", "final": true, "seq": 3}`` — a line of
  speech (PRD §8.9). Finals are persisted then broadcast; interim frames are
  broadcast only, so the room watches words appear without paying 15x the writes.

**Outbound frames**

* ``{"type": "roster", "members": [...]}`` and ``{"type": "presence", ...}``
* ``{"type": "message", "message": {...}}``
* ``{"type": "transcript", "segment": {...}, "final": bool}``
* ``{"type": "transcript_history", "segments": [...]}`` on join, so a late
  arrival sees the script so far rather than only what is said after them.

Transcripts share this socket rather than opening a third one: fewer
connections, and speech and chat stay in one ordered stream.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.db.session import AsyncSessionLocal
from app.realtime.connection_manager import manager
from app.repositories.message import MessageRepository
from app.repositories.participant import ParticipantRepository
from app.repositories.room import RoomRepository
from app.repositories.transcript import TranscriptRepository
from app.repositories.user import UserRepository
from app.schemas.message import MessageRead
from app.schemas.transcript import TranscriptSegmentIn, TranscriptSegmentRead
from app.services import moderation
from app.services.conversation import ConversationService
from app.services.transcript import TranscriptService, forget_speaker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])

#: How much script a joiner is handed. Enough to read the room, small enough
#: that joining a long session is not a multi-megabyte frame.
_HISTORY_LIMIT = 50


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
    await _send_transcript_history(websocket, room_uuid)
    await manager.broadcast(
        room_id, {"type": "presence", "event": "join", "name": name, "user_id": user_id}
    )

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "transcript":
                await _handle_transcript(websocket, room_id, room_uuid, user_uuid, name, data)
                continue

            # No `type` (or any other value) with `text` is a chat message —
            # the original contract, kept so existing clients keep working.
            text = (data.get("text") or "").strip()
            if not text:
                continue
            await _handle_message(websocket, room_id, room_uuid, user_uuid, text)
    except WebSocketDisconnect:
        manager.disconnect(room_id, websocket)
        forget_speaker(room_id, user_id)
        await manager.broadcast(
            room_id, {"type": "presence", "event": "leave", "name": name, "user_id": user_id}
        )


async def _send_transcript_history(websocket: WebSocket, room_uuid: uuid.UUID) -> None:
    """Give a joiner the script so far. Never fatal — a room without history is
    still a working room."""
    try:
        async with AsyncSessionLocal() as session:
            segments = await TranscriptRepository(session).list_for_room(
                room_uuid, limit=_HISTORY_LIMIT
            )
            payload = [
                TranscriptSegmentRead.model_validate(s).model_dump(mode="json")
                for s in segments
            ]
        await websocket.send_json({"type": "transcript_history", "segments": payload})
    except Exception:  # noqa: BLE001 — history is a nicety, not a precondition
        logger.warning("Could not load transcript history for room %s", room_uuid)


async def _handle_transcript(
    websocket: WebSocket,
    room_id: str,
    room_uuid: uuid.UUID,
    user_uuid: uuid.UUID,
    name: str,
    data: dict,
) -> None:
    try:
        payload = TranscriptSegmentIn.model_validate(data)
    except ValidationError:
        # A malformed speech frame is dropped silently. Speech arrives several
        # times a second; erroring back would spam a live room over one bad line.
        return

    if not payload.final:
        # Interim: broadcast so the room sees words appearing, never stored.
        # Keyed by (user_id, seq) so the client replaces its own preview rather
        # than appending a new line each time.
        await manager.broadcast(
            room_id,
            {
                "type": "transcript",
                "final": False,
                "segment": {
                    "user_id": str(user_uuid),
                    "speaker_name": name,
                    "text": payload.text,
                    "seq": payload.seq,
                    "spoken_at": (payload.spoken_at or datetime.now(UTC)).isoformat(),
                },
            },
        )
        return

    async with AsyncSessionLocal() as session:
        service = TranscriptService(TranscriptRepository(session))
        try:
            segment = await service.record_final(room_uuid, user_uuid, name, payload)
            if segment is None:
                await session.rollback()
                return  # throttled or empty — drop quietly
            await session.commit()
        except Exception:  # noqa: BLE001 — never kill the socket over one line
            await session.rollback()
            logger.warning("Could not store transcript segment for room %s", room_uuid)
            return
        body = TranscriptSegmentRead.model_validate(segment).model_dump(mode="json")

    await manager.broadcast(room_id, {"type": "transcript", "final": True, "segment": body})


async def _handle_message(
    websocket: WebSocket,
    room_id: str,
    room_uuid: uuid.UUID,
    user_uuid: uuid.UUID,
    text: str,
) -> None:
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
            await websocket.send_json({"type": "error", "message": "Could not send message"})
            return
        payload = MessageRead.model_validate(message).model_dump(mode="json")

    await manager.broadcast(room_id, {"type": "message", "message": payload})
