"""In-memory WebSocket fan-out, grouped by room.

Single-process only — fine for the demo and a single API instance. To scale out
across workers, back this with Redis pub/sub (see docs/06_Architecture.md); the
public interface here stays the same.

Each connection carries its user's id and name so a newcomer can be handed the
current roster (who is already in the room) on connect — without this, a client
only learns about members who join *after* it, and misses everyone already there.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket


@dataclass
class _Connection:
    websocket: WebSocket
    user_id: str
    name: str


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, dict[WebSocket, _Connection]] = defaultdict(dict)

    async def connect(self, room_id: str, websocket: WebSocket, user_id: str, name: str) -> None:
        await websocket.accept()
        self._rooms[room_id][websocket] = _Connection(websocket, user_id, name)

    def disconnect(self, room_id: str, websocket: WebSocket) -> None:
        connections = self._rooms.get(room_id)
        if connections is None:
            return
        connections.pop(websocket, None)
        if not connections:
            del self._rooms[room_id]

    def roster(self, room_id: str) -> list[dict[str, str]]:
        """Current members in the room, de-duplicated by user (one entry per user
        even if they have several tabs open)."""
        by_user: dict[str, str] = {}
        for conn in self._rooms.get(room_id, {}).values():
            by_user[conn.user_id] = conn.name
        return [{"user_id": uid, "name": name} for uid, name in by_user.items()]

    async def broadcast(self, room_id: str, payload: dict[str, Any]) -> None:
        # Iterate a copy so a send failure mid-loop can prune without mutating live.
        for websocket in list(self._rooms.get(room_id, {})):
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001 — drop a dead socket, keep broadcasting
                self.disconnect(room_id, websocket)


# Process-wide singleton shared by all WebSocket connections.
manager = ConnectionManager()
