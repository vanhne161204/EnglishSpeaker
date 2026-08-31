"""Profile endpoints — always the authenticated caller, never an id from the URL.

`POST /users` and `/users/{id}` were removed: they let anyone create a
password-free account and edit anybody's profile (docs/11_Security.md §11.4).
"""

from httpx import AsyncClient


async def test_my_profile_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/users/me")).status_code == 401
    assert (await client.patch("/api/v1/users/me", json={"level": "b1"})).status_code == 401


async def test_get_my_profile(user_client: AsyncClient) -> None:
    resp = await user_client.get("/api/v1/users/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "learner"


async def test_update_my_profile(user_client: AsyncClient) -> None:
    resp = await user_client.patch(
        "/api/v1/users/me", json={"level": "beginner", "interests": "travel,music"}
    )
    assert resp.status_code == 200
    assert resp.json()["level"] == "beginner"
    # And it persisted.
    assert (await user_client.get("/api/v1/users/me")).json()["interests"] == "travel,music"


async def test_there_is_no_way_to_read_another_profile(
    user_client: AsyncClient, other_client: AsyncClient
) -> None:
    """The old `/users/{id}` route is gone; a caller can only ever see themselves."""
    mine = (await user_client.get("/api/v1/users/me")).json()
    theirs = (await other_client.get("/api/v1/users/me")).json()
    assert mine["id"] != theirs["id"]
    # No route accepts someone else's id.
    assert (await user_client.get(f"/api/v1/users/{theirs['id']}")).status_code == 404
