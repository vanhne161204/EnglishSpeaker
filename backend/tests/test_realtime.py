"""Unit tests for the WebSocket fan-out (no real sockets needed)."""

from typing import Any

from app.realtime.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[dict[str, Any]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)


async def test_broadcast_reaches_every_socket_in_room() -> None:
    manager = ConnectionManager()
    a, b = FakeWebSocket(), FakeWebSocket()
    await manager.connect("room-1", a, "user-a", "A")  # type: ignore[arg-type]
    await manager.connect("room-1", b, "user-b", "B")  # type: ignore[arg-type]
    assert a.accepted and b.accepted

    await manager.broadcast("room-1", {"type": "message", "n": 1})
    assert a.sent == [{"type": "message", "n": 1}]
    assert b.sent == [{"type": "message", "n": 1}]


async def test_disconnect_stops_delivery() -> None:
    manager = ConnectionManager()
    a, b = FakeWebSocket(), FakeWebSocket()
    await manager.connect("room-1", a, "user-a", "A")  # type: ignore[arg-type]
    await manager.connect("room-1", b, "user-b", "B")  # type: ignore[arg-type]

    manager.disconnect("room-1", a)  # type: ignore[arg-type]
    await manager.broadcast("room-1", {"type": "message", "n": 2})

    assert a.sent == []
    assert b.sent == [{"type": "message", "n": 2}]


async def test_broadcast_to_other_room_is_isolated() -> None:
    manager = ConnectionManager()
    a = FakeWebSocket()
    await manager.connect("room-1", a, "user-a", "A")  # type: ignore[arg-type]

    await manager.broadcast("room-2", {"type": "message", "n": 3})
    assert a.sent == []
