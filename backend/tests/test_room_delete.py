"""Deleting a room: who may, and what goes with it.

Two actors are allowed — the room's owner, and any admin. Neither says which
they are; both are checked against the database, the same rule as every other
authorization decision in this API (docs/11_Security.md §11.1).

The data question matters as much as the permission one. A room delete is not a
tidy-up: it destroys the conversation. These tests pin exactly what is lost and
what survives, because that boundary is easy to move by accident with an
`ondelete` change and hard to notice afterwards.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.message import Message
from app.models.session_report import SessionReport
from app.models.transcript import TranscriptSegment


async def _make_room(client: AsyncClient, title: str = "My room") -> dict:
    resp = await client.post("/api/v1/rooms", json={"title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _count(model) -> int:
    async with AsyncSessionLocal() as session:
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


# --- who may delete ---------------------------------------------------------


async def test_deleting_requires_an_account(client: AsyncClient, admin_client: AsyncClient) -> None:
    room = await _make_room(admin_client)
    anon = AsyncClient(transport=client._transport, base_url="http://test")
    assert (await anon.delete(f"/api/v1/rooms/{room['id']}")).status_code == 401


async def test_the_owner_can_delete_their_own_room(other_client: AsyncClient) -> None:
    room = await _make_room(other_client)
    resp = await other_client.delete(f"/api/v1/rooms/{room['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == room["id"]

    assert (await other_client.get(f"/api/v1/rooms/{room['id']}")).status_code == 404


async def test_an_ordinary_user_cannot_delete_someone_elses_room(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    room = await _make_room(admin_client, "Not yours")
    resp = await other_client.delete(f"/api/v1/rooms/{room['id']}")
    assert resp.status_code == 403
    # And it is still there.
    assert (await other_client.get(f"/api/v1/rooms/{room['id']}")).status_code == 200


async def test_an_admin_can_delete_any_room(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """The point of the admin path: a room full of abuse should not need its own
    host's cooperation to disappear."""
    room = await _make_room(other_client, "Someone else's room")
    assert (await admin_client.delete(f"/api/v1/rooms/{room['id']}")).status_code == 200
    assert (await other_client.get(f"/api/v1/rooms/{room['id']}")).status_code == 404


async def test_deleting_an_unknown_room_is_404(admin_client: AsyncClient) -> None:
    assert (await admin_client.delete(f"/api/v1/rooms/{uuid.uuid4()}")).status_code == 404


async def test_a_matched_room_has_no_owner_so_only_an_admin_can_delete_it(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """`match/random` creates rooms with no owner. Nobody should inherit one by
    being the first to ask."""
    room = (await other_client.post("/api/v1/match/random", json={"mode": "normal"})).json()
    assert room["owner_id"] is None

    assert (await other_client.delete(f"/api/v1/rooms/{room['id']}")).status_code == 403
    assert (await admin_client.delete(f"/api/v1/rooms/{room['id']}")).status_code == 200


# --- what it destroys, and what it spares -----------------------------------


async def test_deleting_takes_the_conversation_with_it(other_client: AsyncClient) -> None:
    """Messages and transcript are the room's content and go with the room."""
    room = await _make_room(other_client)
    await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    await other_client.post(f"/api/v1/rooms/{room['id']}/messages", json={"text": "hello"})

    async with AsyncSessionLocal() as session:
        me = (await other_client.get("/api/v1/users/me")).json()["id"]
        session.add(
            TranscriptSegment(
                room_id=uuid.UUID(room["id"]),
                user_id=uuid.UUID(me),
                speaker_name="Other",
                text="I said something",
                spoken_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            )
        )
        await session.commit()

    assert await _count(Message) == 1
    assert await _count(TranscriptSegment) == 1

    assert (await other_client.delete(f"/api/v1/rooms/{room['id']}")).status_code == 200

    assert await _count(Message) == 0
    assert await _count(TranscriptSegment) == 0


async def test_a_learners_own_report_survives_the_room(other_client: AsyncClient) -> None:
    """A coach report is the learner's record of their own practice. Losing it to
    somebody else's tidy-up would be wrong, so the room reference goes NULL
    instead of cascading."""
    room = await _make_room(other_client)
    me = (await other_client.get("/api/v1/users/me")).json()["id"]

    async with AsyncSessionLocal() as session:
        session.add(
            SessionReport(
                user_id=uuid.UUID(me),
                room_id=uuid.UUID(room["id"]),
                band_fluency=6.0,
                band_lexical=6.0,
                band_grammar=6.0,
                band_overall=6.0,
                summary="Good session",
                next_band=6.5,
                criteria={},
                blockers=[],
                drills=[],
                metrics={},
                model="test",
            )
        )
        await session.commit()

    await other_client.delete(f"/api/v1/rooms/{room['id']}")

    assert await _count(SessionReport) == 1, "the learner's report must survive"
    async with AsyncSessionLocal() as session:
        report = (await session.execute(select(SessionReport))).scalar_one()
        assert report.room_id is None


async def test_the_count_of_people_ejected_comes_back(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """Deleting a busy room throws real people out mid-conversation. The caller
    should be able to say how many."""
    room = await _make_room(admin_client)
    await admin_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})

    resp = await admin_client.delete(f"/api/v1/rooms/{room['id']}")
    assert resp.json()["participants_removed"] == 2


# --- audit ------------------------------------------------------------------


async def test_an_admin_deleting_someone_elses_room_is_logged(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    room = await _make_room(other_client, "Their room")
    await admin_client.delete(f"/api/v1/rooms/{room['id']}")

    entries = (await admin_client.get("/api/v1/admin/audit")).json()
    assert any(e["action"] == "room.delete" for e in entries)
    entry = next(e for e in entries if e["action"] == "room.delete")
    assert entry["target_name"] == "Their room"
    assert entry["actor_name"] == "Admin"


async def test_deleting_your_own_room_is_not_an_admin_action(
    admin_client: AsyncClient,
) -> None:
    """An owner tidying up their own room is ordinary use, not a privileged act
    on someone else's content. A log full of non-events is a log nobody reads."""
    room = await _make_room(admin_client, "Mine")
    await admin_client.delete(f"/api/v1/rooms/{room['id']}")

    entries = (await admin_client.get("/api/v1/admin/audit")).json()
    assert not any(e["action"] == "room.delete" for e in entries)


async def test_people_still_inside_are_told_over_the_socket(
    admin_client: AsyncClient, monkeypatch
) -> None:
    """Without this the page stays open and every request starts 404ing, which
    reads as the app being broken rather than the room being gone."""
    sent: list[tuple[str, dict]] = []

    async def _capture(room_id: str, payload: dict) -> None:
        sent.append((room_id, payload))

    from app.api.v1.routes import rooms as rooms_route

    monkeypatch.setattr(rooms_route.manager, "broadcast", _capture)

    room = await _make_room(admin_client)
    await admin_client.delete(f"/api/v1/rooms/{room['id']}")

    assert sent == [(room["id"], {"type": "room_closed", "reason": "The host closed this room."})]


async def test_nothing_is_broadcast_when_the_delete_is_refused(
    admin_client: AsyncClient, other_client: AsyncClient, monkeypatch
) -> None:
    """A rejected delete must not tell the room it closed."""
    sent: list[tuple[str, dict]] = []

    async def _capture(room_id: str, payload: dict) -> None:
        sent.append((room_id, payload))

    from app.api.v1.routes import rooms as rooms_route

    monkeypatch.setattr(rooms_route.manager, "broadcast", _capture)

    room = await _make_room(admin_client, "Not yours")
    assert (await other_client.delete(f"/api/v1/rooms/{room['id']}")).status_code == 403
    assert sent == []
