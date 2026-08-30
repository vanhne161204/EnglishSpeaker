"""Live transcripts and the REST views of them (PRD §8.9).

The transcript is the input to every AI feature in docs/10_AI_Design.md, so the
rules asserted here are load-bearing: finals stored, interim discarded, chat
unaffected, and one learner never able to touch another's script.

WebSocket behaviour is exercised by calling the frame handlers directly with a
``FakeWebSocket``, matching the convention in ``test_realtime.py`` — httpx has no
WebSocket client, and a sync ``TestClient`` would fight the async DB fixtures.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.v1.routes.ws import _handle_transcript
from app.db.session import AsyncSessionLocal
from app.models.transcript import TranscriptSegment
from app.realtime.connection_manager import manager
from app.repositories.transcript import TranscriptRepository
from app.schemas.transcript import TranscriptSegmentIn
from app.services import transcript as transcript_service
from app.services.transcript import MAX_FINALS_PER_MINUTE, TranscriptService


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def accept(self) -> None: ...

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)


@pytest.fixture(autouse=True)
def _clear_speaker_throttle():
    """The throttle is a module-level dict; reset it so a chatty test does not
    silence the next one."""
    transcript_service._recent.clear()
    yield
    transcript_service._recent.clear()


async def _room_and_speaker(client: AsyncClient) -> tuple[uuid.UUID, uuid.UUID, str, str]:
    """Create a room and a registered speaker. Returns (room, user, name, token)."""
    room = (
        await client.post("/api/v1/rooms", json={"title": "Speaking", "mode": "normal"})
    ).json()
    auth = (
        await client.post(
            "/api/v1/auth/register",
            json={"username": f"sp{uuid.uuid4().hex[:8]}", "password": "pw12345678"},
        )
    ).json()
    return (
        uuid.UUID(room["id"]),
        uuid.UUID(auth["user"]["id"]),
        auth["user"]["display_name"] or auth["user"]["username"],
        auth["token"],
    )


def _as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo even on ``DateTime(timezone=True)``; Postgres keeps it.
    Normalise so the same assertion holds on both."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def _stored(room_id: uuid.UUID) -> list[TranscriptSegment]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.room_id == room_id)
            .order_by(TranscriptSegment.spoken_at)
        )
        return list(rows.scalars())


async def _speak(room_id, user_id, name, text, *, final=True, seq=0, **extra):
    """Push one speech frame through the real handler."""
    socket = FakeWebSocket()
    await manager.connect(str(room_id), socket, str(user_id), name)  # type: ignore[arg-type]
    try:
        await _handle_transcript(
            socket,  # type: ignore[arg-type]
            str(room_id),
            room_id,
            user_id,
            name,
            {"type": "transcript", "text": text, "final": final, "seq": seq, **extra},
        )
    finally:
        manager.disconnect(str(room_id), socket)  # type: ignore[arg-type]
    return socket.sent


# --- the core rule: finals are kept, interim is not -----------------------


async def test_a_final_segment_is_stored_and_broadcast(client: AsyncClient) -> None:
    room_id, user_id, name, _ = await _room_and_speaker(client)

    sent = await _speak(room_id, user_id, name, "I went to Da Nang last weekend.")

    assert len(sent) == 1
    assert sent[0]["type"] == "transcript"
    assert sent[0]["final"] is True
    assert sent[0]["segment"]["text"] == "I went to Da Nang last weekend."
    assert sent[0]["segment"]["speaker_name"] == name

    stored = await _stored(room_id)
    assert len(stored) == 1
    assert stored[0].text == "I went to Da Nang last weekend."


async def test_an_interim_segment_is_broadcast_but_never_stored(client: AsyncClient) -> None:
    """Interim results arrive several times a second. Storing them would multiply
    writes ~15x for text that is replaced a moment later."""
    room_id, user_id, name, _ = await _room_and_speaker(client)

    sent = await _speak(room_id, user_id, name, "I went to Da", final=False, seq=1)

    assert len(sent) == 1
    assert sent[0]["final"] is False
    assert sent[0]["segment"]["text"] == "I went to Da"
    assert await _stored(room_id) == []


async def test_the_interim_then_final_pair_leaves_exactly_one_row(
    client: AsyncClient,
) -> None:
    """The real shape of speech: several previews, then the finished sentence."""
    room_id, user_id, name, _ = await _room_and_speaker(client)

    for partial in ("I", "I went", "I went to Da"):
        await _speak(room_id, user_id, name, partial, final=False, seq=1)
    await _speak(room_id, user_id, name, "I went to Da Nang.", final=True, seq=1)

    stored = await _stored(room_id)
    assert len(stored) == 1
    assert stored[0].text == "I went to Da Nang."
    assert stored[0].seq == 1


# --- guards ---------------------------------------------------------------


async def test_a_malformed_frame_is_dropped_without_killing_the_socket(
    client: AsyncClient,
) -> None:
    """Speech arrives many times a second; erroring back would spam a live room."""
    room_id, user_id, name, _ = await _room_and_speaker(client)

    sent = await _speak(room_id, user_id, name, "")  # empty text fails validation

    assert sent == []
    assert await _stored(room_id) == []


async def test_an_over_long_segment_is_rejected(client: AsyncClient) -> None:
    room_id, user_id, name, _ = await _room_and_speaker(client)

    sent = await _speak(room_id, user_id, name, "x" * 501)

    assert sent == []
    assert await _stored(room_id) == []


async def test_a_runaway_speaker_is_throttled(client: AsyncClient) -> None:
    """A stuck client, or a radio left next to a mic, must not fill the table."""
    room_id, user_id, name, _ = await _room_and_speaker(client)

    for i in range(MAX_FINALS_PER_MINUTE + 10):
        await _speak(room_id, user_id, name, f"line {i}", seq=i)

    stored = await _stored(room_id)
    assert len(stored) == MAX_FINALS_PER_MINUTE


async def test_the_throttle_is_per_speaker_not_per_room(client: AsyncClient) -> None:
    """One loud speaker must not silence everyone else in the room."""
    room_id, noisy, noisy_name, _ = await _room_and_speaker(client)
    _, quiet, quiet_name, _ = await _room_and_speaker(client)

    for i in range(MAX_FINALS_PER_MINUTE + 5):
        await _speak(room_id, noisy, noisy_name, f"noise {i}", seq=i)
    sent = await _speak(room_id, quiet, quiet_name, "Can I say something?")

    assert len(sent) == 1
    texts = [s.text for s in await _stored(room_id)]
    assert "Can I say something?" in texts


# --- service-level behaviour ----------------------------------------------


async def test_the_client_clock_is_used_for_ordering_when_given(
    client: AsyncClient,
) -> None:
    """`spoken_at` measures the GAP between segments, which is what the fluency
    metrics in docs/10_AI_Design.md §10.3.8 are computed from."""
    room_id, user_id, name, _ = await _room_and_speaker(client)
    when = datetime.now(UTC) - timedelta(minutes=5)

    async with AsyncSessionLocal() as session:
        service = TranscriptService(TranscriptRepository(session))
        await service.record_final(
            room_id,
            user_id,
            name,
            TranscriptSegmentIn(text="said five minutes ago", spoken_at=when),
        )
        await session.commit()

    stored = await _stored(room_id)
    assert abs((_as_utc(stored[0].spoken_at) - when).total_seconds()) < 1


async def test_stt_confidence_is_captured_when_the_engine_reports_it(
    client: AsyncClient,
) -> None:
    """Cannot be backfilled — once the session ends the score is gone (§10.3.11)."""
    room_id, user_id, name, _ = await _room_and_speaker(client)

    await _speak(room_id, user_id, name, "hello there", stt_confidence=0.82)

    assert (await _stored(room_id))[0].stt_confidence == pytest.approx(0.82)


# --- REST views -----------------------------------------------------------


async def test_the_room_script_reads_back_oldest_first(client: AsyncClient) -> None:
    room_id, user_id, name, _ = await _room_and_speaker(client)
    for i, line in enumerate(["First thing.", "Second thing.", "Third thing."]):
        await _speak(room_id, user_id, name, line, seq=i)

    resp = await client.get(f"/api/v1/transcripts/rooms/{room_id}")

    assert resp.status_code == 200
    texts = [s["text"] for s in resp.json()["segments"]]
    assert texts == ["First thing.", "Second thing.", "Third thing."]


async def test_the_room_script_can_be_filtered_to_one_speaker(
    client: AsyncClient,
) -> None:
    """Coach Report grades one learner at a time (docs §10.3.0)."""
    room_id, alice, alice_name, _ = await _room_and_speaker(client)
    _, bob, bob_name, _ = await _room_and_speaker(client)

    await _speak(room_id, alice, alice_name, "Alice speaking.")
    await _speak(room_id, bob, bob_name, "Bob speaking.")

    resp = await client.get(f"/api/v1/transcripts/rooms/{room_id}?speaker_id={alice}")

    texts = [s["text"] for s in resp.json()["segments"]]
    assert texts == ["Alice speaking."]


async def test_my_transcript_needs_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/transcripts/me")).status_code == 401


async def test_my_transcript_returns_only_my_own_lines(client: AsyncClient) -> None:
    """Filtered on the authenticated user, never a query parameter — an id in the
    URL would let anyone read anyone."""
    room_id, alice, alice_name, alice_token = await _room_and_speaker(client)
    _, bob, bob_name, _ = await _room_and_speaker(client)

    await _speak(room_id, alice, alice_name, "Alice said this.")
    await _speak(room_id, bob, bob_name, "Bob said this.")

    resp = await client.get(
        "/api/v1/transcripts/me", headers={"Authorization": f"Bearer {alice_token}"}
    )

    texts = [s["text"] for s in resp.json()["segments"]]
    assert texts == ["Alice said this."]


async def test_deleting_my_transcript_leaves_everyone_elses_alone(
    client: AsyncClient,
) -> None:
    """A learner may erase what they said, never what anybody else said."""
    room_id, alice, alice_name, alice_token = await _room_and_speaker(client)
    _, bob, bob_name, _ = await _room_and_speaker(client)

    await _speak(room_id, alice, alice_name, "Alice said this.")
    await _speak(room_id, bob, bob_name, "Bob said this.")

    resp = await client.request(
        "DELETE",
        "/api/v1/transcripts/me",
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    assert [s.text for s in await _stored(room_id)] == ["Bob said this."]


async def test_paging_walks_backwards_through_time(client: AsyncClient) -> None:
    room_id, user_id, name, _ = await _room_and_speaker(client)
    base = datetime.now(UTC) - timedelta(minutes=10)
    async with AsyncSessionLocal() as session:
        service = TranscriptService(TranscriptRepository(session))
        for i in range(5):
            await service.record_final(
                room_id,
                user_id,
                name,
                TranscriptSegmentIn(text=f"line {i}", spoken_at=base + timedelta(seconds=i)),
            )
        await session.commit()

    first = (await client.get(f"/api/v1/transcripts/rooms/{room_id}?limit=2")).json()
    assert [s["text"] for s in first["segments"]] == ["line 3", "line 4"]

    older = (
        await client.get(
            f"/api/v1/transcripts/rooms/{room_id}?limit=2&before={first['next_before']}"
        )
    ).json()
    assert [s["text"] for s in older["segments"]] == ["line 1", "line 2"]


# --- version-mismatch safety (observed in production 2026-08-30) ----------
#
# The frontend deployed before the backend, and every spoken word — including
# ~3 interim previews per second — became a chat message, because the older
# socket loop was:
#
#     text = (data.get("text") or "").strip()
#     if text: post_chat_message(text)     # `type` never read
#
# The wire key is now `transcript_text`, so such a server finds nothing and
# skips the frame instead of flooding the room.


def test_the_wire_key_cannot_be_mistaken_for_a_chat_message() -> None:
    """The property that makes a version mismatch harmless."""
    frame = {
        "type": "transcript",
        "transcript_text": "I went to Da Nang last weekend",
        "final": True,
        "seq": 0,
    }
    # Verbatim logic from the backend that predates this feature.
    legacy_chat_text = (frame.get("text") or "").strip()
    assert legacy_chat_text == "", "an old backend would post this to chat"

    # The current backend still reads it correctly.
    assert TranscriptSegmentIn.model_validate(frame).text == "I went to Da Nang last weekend"


def test_the_old_wire_key_still_works() -> None:
    """Clients cached mid-rollout keep working; only the safety property is lost."""
    assert TranscriptSegmentIn.model_validate({"text": "hello", "final": True}).text == "hello"


async def test_a_frame_sent_the_new_way_is_stored_normally(client: AsyncClient) -> None:
    room_id, user_id, name, _ = await _room_and_speaker(client)
    socket = FakeWebSocket()
    await manager.connect(str(room_id), socket, str(user_id), name)  # type: ignore[arg-type]
    try:
        await _handle_transcript(
            socket,  # type: ignore[arg-type]
            str(room_id),
            room_id,
            user_id,
            name,
            {"type": "transcript", "transcript_text": "Spoken with the new key.", "final": True},
        )
    finally:
        manager.disconnect(str(room_id), socket)  # type: ignore[arg-type]

    assert [s.text for s in await _stored(room_id)] == ["Spoken with the new key."]
