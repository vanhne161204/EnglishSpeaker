import uuid

from httpx import AsyncClient


async def test_create_and_get_user(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/users",
        json={"display_name": "Alice", "level": "beginner", "interests": "travel,music"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["display_name"] == "Alice"

    got = await client.get(f"/api/v1/users/{body['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]


async def test_get_unknown_user_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_create_user_requires_name(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/users", json={"display_name": ""})
    assert resp.status_code == 422
