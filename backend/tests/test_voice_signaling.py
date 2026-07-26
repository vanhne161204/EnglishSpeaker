"""Unit tests for the WebRTC voice signaling relay (no real sockets needed)."""

from typing import Any

from app.realtime.voice_manager import VoiceSignalingManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)


async def test_others_excludes_caller_and_lists_present_peers() -> None:
    mgr = VoiceSignalingManager()
    a, b = FakeWebSocket(), FakeWebSocket()
    mgr.add("room-1", "alice", "Alice", a)  # type: ignore[arg-type]
    mgr.add("room-1", "bob", "Bob", b)  # type: ignore[arg-type]

    others_for_carol = mgr.others("room-1", "carol")
    assert {p["id"] for p in others_for_carol} == {"alice", "bob"}
    assert mgr.others("room-1", "alice") == [{"id": "bob", "name": "Bob"}]


async def test_send_to_targets_one_peer() -> None:
    mgr = VoiceSignalingManager()
    a, b = FakeWebSocket(), FakeWebSocket()
    mgr.add("room-1", "alice", "Alice", a)  # type: ignore[arg-type]
    mgr.add("room-1", "bob", "Bob", b)  # type: ignore[arg-type]

    ok = await mgr.send_to("room-1", "bob", {"type": "offer", "from": "alice"})
    assert ok is True
    assert b.sent == [{"type": "offer", "from": "alice"}]
    assert a.sent == []  # not echoed back to the sender


async def test_send_to_missing_peer_returns_false() -> None:
    mgr = VoiceSignalingManager()
    assert await mgr.send_to("room-1", "ghost", {"type": "offer"}) is False


async def test_broadcast_excludes_sender() -> None:
    mgr = VoiceSignalingManager()
    a, b, c = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()
    mgr.add("room-1", "alice", "Alice", a)  # type: ignore[arg-type]
    mgr.add("room-1", "bob", "Bob", b)  # type: ignore[arg-type]
    mgr.add("room-1", "carol", "Carol", c)  # type: ignore[arg-type]

    await mgr.broadcast("room-1", {"type": "peer-left", "peer": {"id": "alice"}}, exclude="alice")
    assert a.sent == []
    assert b.sent and c.sent


async def test_remove_cleans_up_empty_room() -> None:
    mgr = VoiceSignalingManager()
    a = FakeWebSocket()
    mgr.add("room-1", "alice", "Alice", a)  # type: ignore[arg-type]
    mgr.remove("room-1", "alice")
    assert mgr.others("room-1", "anyone") == []
