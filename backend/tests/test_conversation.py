"""Room membership and messages.

Every actor is the authenticated caller. These used to pass a `user_id` in the
body, which let a caller join, leave or post as somebody else
(docs/11_Security.md §11.4).
"""

import uuid

from httpx import AsyncClient


async def _room(client: AsyncClient, endpoint: str = "/api/v1/match/random") -> dict:
    return (await client.post(endpoint, json={"mode": "normal"})).json()


async def test_room_actions_require_authentication(client: AsyncClient) -> None:
    room_id = uuid.uuid4()
    assert (await client.post(f"/api/v1/rooms/{room_id}/join", json={})).status_code == 401
    assert (await client.post(f"/api/v1/rooms/{room_id}/leave")).status_code == 401
    assert (
        await client.post(f"/api/v1/rooms/{room_id}/messages", json={"text": "hi"})
    ).status_code == 401


async def test_join_and_leave_update_participant_count(user_client: AsyncClient) -> None:
    room = await _room(user_client)
    before = room["participant_count"]

    joined = await user_client.post(
        f"/api/v1/rooms/{room['id']}/join", json={"display_name": "Alice"}
    )
    assert joined.status_code == 200
    assert joined.json()["participant_count"] == before + 1

    # Joining again is idempotent — no double counting.
    again = await user_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    assert again.json()["participant_count"] == before + 1

    left = await user_client.post(f"/api/v1/rooms/{room['id']}/leave")
    assert left.json()["participant_count"] == before


async def test_join_unknown_room_returns_404(user_client: AsyncClient) -> None:
    resp = await user_client.post(f"/api/v1/rooms/{uuid.uuid4()}/join", json={})
    assert resp.status_code == 404


async def test_one_on_one_room_rejects_a_third_person(
    user_client: AsyncClient, other_client: AsyncClient
) -> None:
    room = await _room(user_client, "/api/v1/match/one")
    join_url = f"/api/v1/rooms/{room['id']}/join"

    assert (await user_client.post(join_url, json={})).status_code == 200
    assert (await other_client.post(join_url, json={})).status_code == 200

    # A third account cannot squeeze in.
    third = await other_client.post(
        "/api/v1/auth/register",
        json={"username": f"third{uuid.uuid4().hex[:6]}", "password": "pw12345678"},
    )
    full = await other_client.post(
        join_url, json={}, headers={"Authorization": f"Bearer {third.json()['token']}"}
    )
    assert full.status_code == 409


async def test_messages_persist_and_list_oldest_first(user_client: AsyncClient) -> None:
    room = await _room(user_client)
    await user_client.post(f"/api/v1/rooms/{room['id']}/join", json={})

    sent = await user_client.post(
        f"/api/v1/rooms/{room['id']}/messages", json={"text": "Hello there!"}
    )
    assert sent.status_code == 201
    # The sender is the token holder, not a name supplied by the caller.
    assert sent.json()["sender_name"] == "Learner"

    history = await user_client.get(f"/api/v1/rooms/{room['id']}/messages")
    assert history.status_code == 200
    assert [m["text"] for m in history.json()] == ["Hello there!"]


async def test_a_message_cannot_be_posted_as_someone_else(user_client: AsyncClient) -> None:
    """The body has no `user_id` field at all, so a forged sender is impossible
    rather than merely rejected."""
    room = await _room(user_client)
    await user_client.post(f"/api/v1/rooms/{room['id']}/join", json={})

    sent = await user_client.post(
        f"/api/v1/rooms/{room['id']}/messages",
        json={"text": "hi", "user_id": str(uuid.uuid4())},  # ignored
    )
    assert sent.status_code == 201
    assert sent.json()["sender_name"] == "Learner"
