"""Plan endpoints, scoped to the caller.

These used to take a `user_id` from the path, so anyone could grant themselves
premium — or downgrade somebody else (docs/11_Security.md §11.4).
"""

from httpx import AsyncClient


async def test_subscription_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/users/me/subscription")).status_code == 401
    assert (
        await client.put("/api/v1/users/me/subscription", json={"plan": "premium"})
    ).status_code == 401


async def test_a_new_account_is_on_the_free_plan(user_client: AsyncClient) -> None:
    resp = await user_client.get("/api/v1/users/me/subscription")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "free"
    assert body["limits"]["ai_suggestions_per_day"] == 10


async def test_upgrade_and_cancel(user_client: AsyncClient) -> None:
    upgraded = await user_client.put(
        "/api/v1/users/me/subscription", json={"plan": "premium"}
    )
    assert upgraded.status_code == 200
    assert upgraded.json()["plan"] == "premium"
    assert upgraded.json()["limits"]["ai_suggestions_per_day"] is None  # unlimited

    # The change persists on the profile.
    assert (await user_client.get("/api/v1/users/me")).json()["plan"] == "premium"

    cancelled = await user_client.put("/api/v1/users/me/subscription", json={"plan": "free"})
    assert cancelled.json()["plan"] == "free"


async def test_plan_is_validated(user_client: AsyncClient) -> None:
    bad = await user_client.put("/api/v1/users/me/subscription", json={"plan": "gold"})
    assert bad.status_code == 422


async def test_upgrading_cannot_touch_another_account(
    user_client: AsyncClient, other_client: AsyncClient
) -> None:
    """The regression that mattered: no route accepts a target user id."""
    await user_client.put("/api/v1/users/me/subscription", json={"plan": "premium"})
    assert (await other_client.get("/api/v1/users/me/subscription")).json()["plan"] == "free"
