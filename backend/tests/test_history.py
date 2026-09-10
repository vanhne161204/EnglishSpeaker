"""Practice history (PRD §8.13), and who may read a room's conversation.

History is the first feature that reads a room's transcript AFTER the learner
has left. That exposed the transcript route having no check at all, so the
access rule is pinned here, next to the feature that depends on it.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient

from app.db.session import AsyncSessionLocal
from app.models.feedback import SentenceFeedback
from app.models.session_report import SessionReport
from app.models.transcript import TranscriptSegment


async def _me(client: AsyncClient) -> str:
    return (await client.get("/api/v1/users/me")).json()["id"]


async def _room(client: AsyncClient, title: str = "Travel chat") -> str:
    resp = await client.post("/api/v1/rooms", json={"title": title, "topic": "Travel"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _join(client: AsyncClient, room_id: str) -> None:
    resp = await client.post(f"/api/v1/rooms/{room_id}/join", json={})
    assert resp.status_code == 200, resp.text


async def _say(room_id: str, user_id: str, text: str, name: str = "Learner") -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            TranscriptSegment(
                room_id=uuid.UUID(room_id),
                user_id=uuid.UUID(user_id),
                speaker_name=name,
                text=text,
                spoken_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def _graded(room_id: str, user_id: str, *, correct: int, wrong: int) -> None:
    """Coach report layer 1 rows: `correct` good sentences, `wrong` with mistakes."""
    async with AsyncSessionLocal() as session:
        for i in range(correct + wrong):
            session.add(
                SentenceFeedback(
                    user_id=uuid.UUID(user_id),
                    room_id=uuid.UUID(room_id),
                    original_text=f"sentence {i}",
                    text_hash=uuid.uuid4().hex,
                    is_correct=i < correct,
                )
            )
        await session.commit()


async def _banded(
    room_id: str, user_id: str, overall: str, created_at: datetime | None = None
) -> None:
    """Coach report layer 2: one IELTS band report."""
    band = Decimal(overall)
    async with AsyncSessionLocal() as session:
        report = SessionReport(
            user_id=uuid.UUID(user_id),
            room_id=uuid.UUID(room_id),
            band_fluency=band,
            band_lexical=band,
            band_grammar=band,
            band_overall=band,
            summary=f"Solid session at {overall}.",
            next_band=band + Decimal("0.5"),
            criteria={},
            blockers=[],
            drills=[],
            metrics={},
            model="test",
        )
        if created_at is not None:
            report.created_at = created_at
        session.add(report)
        await session.commit()


async def _history(client: AsyncClient) -> list[dict]:
    resp = await client.get("/api/v1/history/me")
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- the list ---------------------------------------------------------------


async def test_history_requires_an_account(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/history/me")).status_code == 401


async def test_a_new_learner_has_no_history(user_client: AsyncClient) -> None:
    assert await _history(user_client) == []


async def test_a_room_you_joined_appears(user_client: AsyncClient) -> None:
    room_id = await _room(user_client, "Weekend plans")
    await _join(user_client, room_id)

    [item] = await _history(user_client)
    assert item["room_id"] == room_id
    assert item["room_title"] == "Weekend plans"
    assert item["topic"] == "Travel"
    assert item["room_exists"] is True
    assert item["visits"] == 1
    # Nothing said and nothing graded yet: zeros, not missing fields.
    assert item["lines_spoken"] == 0
    assert item["sentences_checked"] == 0
    assert item["band_overall"] is None


async def test_rejoining_counts_visits_instead_of_listing_the_room_twice(
    user_client: AsyncClient,
) -> None:
    room_id = await _room(user_client)
    await _join(user_client, room_id)
    await user_client.post(f"/api/v1/rooms/{room_id}/leave")
    await _join(user_client, room_id)

    [item] = await _history(user_client)
    assert item["visits"] == 2


async def test_the_counts_are_only_your_own(
    user_client: AsyncClient, other_client: AsyncClient
) -> None:
    """Two learners in the same room see the same room, and only their own work.

    Mixing them up would show one learner another's mistakes.
    """
    me, them = await _me(user_client), await _me(other_client)
    room_id = await _room(user_client)
    await _join(user_client, room_id)
    await _join(other_client, room_id)

    await _say(room_id, me, "I went to Da Nang last week.")
    await _say(room_id, me, "The food was great.")
    await _say(room_id, them, "Sounds lovely.", name="Other")
    await _graded(room_id, me, correct=2, wrong=1)
    await _graded(room_id, them, correct=0, wrong=2)
    await _banded(room_id, me, "6.5")
    await _banded(room_id, them, "8.0")

    [mine] = await _history(user_client)
    assert mine["lines_spoken"] == 2
    assert mine["sentences_checked"] == 3
    assert mine["sentences_with_mistakes"] == 1
    assert mine["band_overall"] == 6.5

    [theirs] = await _history(other_client)
    assert theirs["lines_spoken"] == 1
    assert theirs["sentences_checked"] == 2
    assert theirs["sentences_with_mistakes"] == 2
    assert theirs["band_overall"] == 8.0


async def test_another_learners_rooms_are_not_listed(
    user_client: AsyncClient, other_client: AsyncClient
) -> None:
    room_id = await _room(other_client)
    await _join(other_client, room_id)
    assert await _history(user_client) == []


async def test_the_newest_band_report_wins(user_client: AsyncClient) -> None:
    """Asking for a report again adds a row. The old score must not come back."""
    me = await _me(user_client)
    room_id = await _room(user_client)
    await _join(user_client, room_id)
    await _banded(room_id, me, "5.0", created_at=datetime.now(UTC) - timedelta(hours=1))
    await _banded(room_id, me, "7.0")

    [item] = await _history(user_client)
    assert item["band_overall"] == 7.0


async def test_most_recent_first(user_client: AsyncClient) -> None:
    first = await _room(user_client, "Earlier")
    await _join(user_client, first)
    later = await _room(user_client, "Later")
    await _join(user_client, later)

    titles = [item["room_title"] for item in await _history(user_client)]
    assert titles == ["Later", "Earlier"]


async def test_a_deleted_rooms_report_is_still_shown(user_client: AsyncClient) -> None:
    """The conversation goes with the room, but the learner's report is their own
    record. History must not quietly drop it."""
    me = await _me(user_client)
    room_id = await _room(user_client, "Soon gone")
    await _join(user_client, room_id)
    await _banded(room_id, me, "6.0")

    assert (await user_client.delete(f"/api/v1/rooms/{room_id}")).status_code == 200

    [item] = await _history(user_client)
    assert item["room_exists"] is False
    assert item["room_id"] is None
    assert item["band_overall"] == 6.0
    assert item["report_summary"] == "Solid session at 6.0."
    assert item["report_id"] is not None  # a stable key, since there is no room id


async def test_the_band_is_a_json_number(user_client: AsyncClient) -> None:
    """A Decimal would arrive as the string "6.5", and `toFixed` on a string
    throws in the browser."""
    me = await _me(user_client)
    room_id = await _room(user_client)
    await _join(user_client, room_id)
    await _banded(room_id, me, "6.5")

    [item] = await _history(user_client)
    assert isinstance(item["band_overall"], float)


# --- who may read a room's conversation -------------------------------------


async def test_reading_a_conversation_requires_an_account(client: AsyncClient) -> None:
    resp = await client.get(f"/api/v1/transcripts/rooms/{uuid.uuid4()}")
    assert resp.status_code == 401


async def test_knowing_the_room_id_is_not_enough(
    user_client: AsyncClient, other_client: AsyncClient
) -> None:
    """Room ids are public in the room list. Before this check, anyone could read
    every conversation on the site, logged in or not."""
    me = await _me(user_client)
    room_id = await _room(user_client)
    await _join(user_client, room_id)
    await _say(room_id, me, "Something private.")

    resp = await other_client.get(f"/api/v1/transcripts/rooms/{room_id}")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "not_a_member"


async def test_a_past_member_can_still_read_it(user_client: AsyncClient) -> None:
    """The whole point of History: reading a session after you have left it."""
    me = await _me(user_client)
    room_id = await _room(user_client)
    await _join(user_client, room_id)
    await _say(room_id, me, "I said this before leaving.")
    await user_client.post(f"/api/v1/rooms/{room_id}/leave")

    resp = await user_client.get(f"/api/v1/transcripts/rooms/{room_id}")
    assert resp.status_code == 200
    assert [s["text"] for s in resp.json()["segments"]] == ["I said this before leaving."]


async def test_a_current_member_sees_everyone_in_the_conversation(
    user_client: AsyncClient, other_client: AsyncClient
) -> None:
    """Membership opens the whole conversation, not only your own lines: it is
    the context the feedback refers to."""
    me, them = await _me(user_client), await _me(other_client)
    room_id = await _room(user_client)
    await _join(user_client, room_id)
    await _join(other_client, room_id)
    await _say(room_id, me, "Hello.")
    await _say(room_id, them, "Hi there.", name="Other")

    resp = await user_client.get(f"/api/v1/transcripts/rooms/{room_id}")
    assert [s["text"] for s in resp.json()["segments"]] == ["Hello.", "Hi there."]


async def test_the_band_report_card_gets_numbers(user_client: AsyncClient) -> None:
    """The history page shows the saved band report. Its bands went out as
    strings ("6.5"), and the card formats them with toFixed(), so it crashed
    whenever a saved report existed — in the Leave dialog too."""
    me = await _me(user_client)
    room_id = await _room(user_client)
    await _join(user_client, room_id)
    await _banded(room_id, me, "6.5")

    body = (await user_client.get(f"/api/v1/reports/rooms/{room_id}")).json()
    for field in ("band_overall", "band_fluency", "band_lexical", "band_grammar", "next_band"):
        assert isinstance(body[field], float), f"{field} = {body[field]!r}"
    assert body["band_overall"] == 6.5

    [point] = (await user_client.get("/api/v1/reports/me/history")).json()
    assert isinstance(point["band_overall"], float)
