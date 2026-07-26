"""WebRTC voice signaling relay, grouped by room.

The server never touches audio — voice flows peer-to-peer (a mesh). This manager
only relays signaling messages (SDP offers/answers and ICE candidates) between the
peers in a room and tracks who is present so peers know whom to call.

Single-process / in-memory, like ``ConnectionManager``. For multi-instance scale,
back the peer registry + relay with Redis pub/sub; the interface stays the same.
An SFU (LiveKit/mediasoup) is the path for large rooms where a full mesh is too
many connections.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket


@dataclass
class VoicePeer:
    websocket: WebSocket
    name: str


class VoiceSignalingManager:
    def __init__(self) -> None:
        # room_id -> peer_id -> VoicePeer
        self._rooms: dict[str, dict[str, VoicePeer]] = defaultdict(dict)

    def others(self, room_id: str, peer_id: str) -> list[dict[str, str]]:
        """Peers already in the room (excluding the caller), as {id, name}."""
        return [
            {"id": pid, "name": peer.name}
            for pid, peer in self._rooms.get(room_id, {}).items()
            if pid != peer_id
        ]

    def add(self, room_id: str, peer_id: str, name: str, websocket: WebSocket) -> None:
        self._rooms[room_id][peer_id] = VoicePeer(websocket=websocket, name=name)

    def remove(self, room_id: str, peer_id: str) -> None:
        peers = self._rooms.get(room_id)
        if peers is None:
            return
        peers.pop(peer_id, None)
        if not peers:
            del self._rooms[room_id]

    async def send_to(self, room_id: str, peer_id: str, payload: dict[str, Any]) -> bool:
        """Relay a message to one peer. Returns False if the peer is gone."""
        peer = self._rooms.get(room_id, {}).get(peer_id)
        if peer is None:
            return False
        try:
            await peer.websocket.send_json(payload)
            return True
        except Exception:  # noqa: BLE001 — treat a dead socket as departed
            self.remove(room_id, peer_id)
            return False

    async def broadcast(
        self, room_id: str, payload: dict[str, Any], exclude: str | None = None
    ) -> None:
        for pid, peer in list(self._rooms.get(room_id, {}).items()):
            if pid == exclude:
                continue
            try:
                await peer.websocket.send_json(payload)
            except Exception:  # noqa: BLE001 — drop a dead socket, keep going
                self.remove(room_id, pid)


# Process-wide singleton shared by all voice signaling connections.
voice_manager = VoiceSignalingManager()
