import uuid

from httpx import AsyncClient


async def _make_user(client: AsyncClient, name: str = "Alice") -> str:
    resp = await client.post("/api/v1/users", json={"display_name": name})
    return resp.json()["id"]


async def _make_room(client: AsyncClient, mode: str = "normal") -> dict:
    return (await client.post("/api/v1/match/random", json={"mode": mode})).json()


async def test_join_and_leave_update_participant_count(client: AsyncClient) -> None:
    user_id = await _make_user(client)
    room = await _make_room(client)
    before = room["participant_count"]

    joined = await client.post(
        f"/api/v1/rooms/{room['id']}/join",
        json={"user_id": user_id, "display_name": "Alice"},
    )
    assert joined.status_code == 200
    assert joined.json()["participant_count"] == before + 1

    # Joining again is idempotent — no double counting.
    again = await client.post(f"/api/v1/rooms/{room['id']}/join", json={"user_id": user_id})
    assert again.json()["participant_count"] == before + 1

    left = await client.post(f"/api/v1/rooms/{room['id']}/leave", json={"user_id": user_id})
    assert left.json()["participant_count"] == before


async def test_join_unknown_room_returns_404(client: AsyncClient) -> None:
    user_id = await _make_user(client)
    resp = await client.post(f"/api/v1/rooms/{uuid.uuid4()}/join", json={"user_id": user_id})
    assert resp.status_code == 404


async def test_one_on_one_room_rejects_third_user(client: AsyncClient) -> None:
    room = (await client.post("/api/v1/match/one", json={"mode": "normal"})).json()
    join_url = f"/api/v1/rooms/{room['id']}/join"
    u1 = await _make_user(client, "A")
    u2 = await _make_user(client, "B")
    u3 = await _make_user(client, "C")

    assert (await client.post(join_url, json={"user_id": u1})).status_code == 200
    assert (await client.post(join_url, json={"user_id": u2})).status_code == 200
    full = await client.post(join_url, json={"user_id": u3})
    assert full.status_code == 409


async def test_messages_persist_and_list_oldest_first(client: AsyncClient) -> None:
    user_id = await _make_user(client, "Bob")
    room = await _make_room(client)
    await client.post(f"/api/v1/rooms/{room['id']}/join", json={"user_id": user_id})

    sent = await client.post(
        f"/api/v1/rooms/{room['id']}/messages",
        json={"user_id": user_id, "text": "Hello there!"},
    )
    assert sent.status_code == 201
    assert sent.json()["sender_name"] == "Bob"

    history = await client.get(f"/api/v1/rooms/{room['id']}/messages")
    assert history.status_code == 200
    assert [m["text"] for m in history.json()] == ["Hello there!"]


async def test_message_from_unknown_user_returns_404(client: AsyncClient) -> None:
    room = await _make_room(client)
    resp = await client.post(
        f"/api/v1/rooms/{room['id']}/messages",
        json={"user_id": str(uuid.uuid4()), "text": "hi"},
    )
    assert resp.status_code == 404
