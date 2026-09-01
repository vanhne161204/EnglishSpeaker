"""The authorization rules from docs/11_Security.md, as executable assertions.

Every test here corresponds to a hole that was live in production. They exist so
the holes cannot be reopened by a refactor that "simplifies" a signature back to
taking an id from the caller.

The one rule: **the server decides who you are; the client never tells it.**
"""

import uuid

from httpx import AsyncClient

from app.api.deps import authenticate_socket

# --- 🔴 anyone could kick anyone from any room ----------------------------


async def test_a_non_owner_cannot_moderate_a_room(
    user_client: AsyncClient, other_client: AsyncClient
) -> None:
    """`owner_id` used to come from the request body, so the ownership check
    compared a database value against a number the attacker chose."""
    room = (
        await user_client.post("/api/v1/rooms", json={"title": "Mine", "mode": "normal"})
    ).json()
    victim = (await user_client.get("/api/v1/users/me")).json()

    resp = await other_client.post(
        f"/api/v1/rooms/{room['id']}/moderate",
        json={"target_user_id": victim["id"], "action": "kick"},
    )
    assert resp.status_code == 403


async def test_moderation_ignores_a_forged_owner_id(
    user_client: AsyncClient, other_client: AsyncClient
) -> None:
    """Even naming the real owner in the body changes nothing — the field is gone."""
    room = (
        await user_client.post("/api/v1/rooms", json={"title": "Mine", "mode": "normal"})
    ).json()
    owner = (await user_client.get("/api/v1/users/me")).json()

    resp = await other_client.post(
        f"/api/v1/rooms/{room['id']}/moderate",
        json={
            "owner_id": owner["id"],  # the exact exploit, now inert
            "target_user_id": owner["id"],
            "action": "kick",
        },
    )
    assert resp.status_code == 403


async def test_the_owner_can_moderate_their_own_room(
    user_client: AsyncClient, other_client: AsyncClient
) -> None:
    room = (
        await user_client.post("/api/v1/rooms", json={"title": "Mine", "mode": "normal"})
    ).json()
    target = (await other_client.get("/api/v1/users/me")).json()

    resp = await user_client.post(
        f"/api/v1/rooms/{room['id']}/moderate",
        json={"target_user_id": target["id"], "action": "mute"},
    )
    assert resp.status_code == 200


async def test_a_room_is_owned_by_whoever_created_it(user_client: AsyncClient) -> None:
    """`owner_id` in the body is ignored; otherwise a caller could create a room
    owned by someone else and then moderate it as them."""
    stranger = uuid.uuid4()
    room = (
        await user_client.post(
            "/api/v1/rooms",
            json={"title": "Mine", "mode": "normal", "owner_id": str(stranger)},
        )
    ).json()
    me = (await user_client.get("/api/v1/users/me")).json()
    assert room["owner_id"] == me["id"]


# --- 🔴 the WebSocket accepted any claimed identity -----------------------


async def test_a_socket_without_a_token_is_rejected() -> None:
    assert await authenticate_socket(None) is None
    assert await authenticate_socket("") is None


async def test_a_socket_with_a_forged_token_is_rejected() -> None:
    assert await authenticate_socket("not-a-jwt") is None
    # A structurally valid JWT signed with the wrong key.
    forged = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDAifQ"
        ".wrongsignature"
    )
    assert await authenticate_socket(forged) is None


async def test_a_valid_token_resolves_to_its_own_user(user_client: AsyncClient) -> None:
    me = (await user_client.get("/api/v1/users/me")).json()
    token = user_client.headers["Authorization"].removeprefix("Bearer ")

    identity = await authenticate_socket(token)

    assert identity is not None
    user_id, name = identity
    assert str(user_id) == me["id"]
    assert name == me["display_name"]


async def test_a_token_for_a_deleted_user_is_rejected(user_client: AsyncClient) -> None:
    """A signature alone is not enough — the account must still exist."""
    from app.core.security import create_access_token

    ghost = create_access_token(uuid.uuid4())
    assert await authenticate_socket(ghost) is None


# --- admin ---------------------------------------------------------------


async def test_content_management_is_admin_only(user_client: AsyncClient) -> None:
    resp = await user_client.post(
        "/api/v1/topics", json={"slug": "sneaky", "title": "Sneaky"}
    )
    assert resp.status_code == 403


async def test_content_management_rejects_anonymous_callers(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/topics", json={"slug": "sneaky", "title": "Sneaky"})
    assert resp.status_code == 401


async def test_admins_can_manage_content(admin_client: AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/v1/topics", json={"slug": "allowed", "title": "Allowed"}
    )
    assert resp.status_code in (200, 201)
