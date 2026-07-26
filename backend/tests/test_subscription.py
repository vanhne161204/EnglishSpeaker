import uuid

from httpx import AsyncClient


async def _make_user(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/users", json={"display_name": "Alice"})
    return resp.json()["id"]


async def test_new_user_is_on_free_plan(client: AsyncClient) -> None:
    user_id = await _make_user(client)
    created = await client.post("/api/v1/users", json={"display_name": "Bob"})
    assert created.json()["plan"] == "free"

    sub = await client.get(f"/api/v1/users/{user_id}/subscription")
    assert sub.status_code == 200
    body = sub.json()
    assert body["plan"] == "free"
    assert body["limits"]["ai_suggestions_per_day"] == 10


async def test_upgrade_and_cancel_plan(client: AsyncClient) -> None:
    user_id = await _make_user(client)

    upgraded = await client.put(f"/api/v1/users/{user_id}/subscription", json={"plan": "premium"})
    assert upgraded.status_code == 200
    assert upgraded.json()["plan"] == "premium"
    assert upgraded.json()["limits"]["ai_suggestions_per_day"] is None  # unlimited

    # The change persists on the profile.
    assert (await client.get(f"/api/v1/users/{user_id}")).json()["plan"] == "premium"

    cancelled = await client.put(f"/api/v1/users/{user_id}/subscription", json={"plan": "free"})
    assert cancelled.json()["plan"] == "free"


async def test_subscription_validates_plan(client: AsyncClient) -> None:
    user_id = await _make_user(client)
    bad = await client.put(f"/api/v1/users/{user_id}/subscription", json={"plan": "gold"})
    assert bad.status_code == 422


async def test_subscription_unknown_user_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/v1/users/{uuid.uuid4()}/subscription")
    assert resp.status_code == 404
