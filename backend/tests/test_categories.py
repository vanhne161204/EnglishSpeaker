import uuid

from httpx import AsyncClient


async def test_category_crud(admin_client: AsyncClient) -> None:
    created = await admin_client.post(
        "/api/v1/categories",
        json={"slug": "daily-life", "name": "Daily Life", "description": "Everyday talk."},
    )
    assert created.status_code == 201
    category = created.json()
    assert category["slug"] == "daily-life"

    listed = await admin_client.get("/api/v1/categories")
    assert listed.status_code == 200
    assert any(c["id"] == category["id"] for c in listed.json())

    got = await admin_client.get(f"/api/v1/categories/{category['id']}")
    assert got.status_code == 200 and got.json()["name"] == "Daily Life"

    updated = await admin_client.patch(
        f"/api/v1/categories/{category['id']}", json={"name": "Everyday Life"}
    )
    assert updated.status_code == 200 and updated.json()["name"] == "Everyday Life"

    deleted = await admin_client.delete(f"/api/v1/categories/{category['id']}")
    assert deleted.status_code == 204
    assert (await admin_client.get(f"/api/v1/categories/{category['id']}")).status_code == 404


async def test_duplicate_category_slug_conflicts(admin_client: AsyncClient) -> None:
    payload = {"slug": "work", "name": "Work"}
    assert (await admin_client.post("/api/v1/categories", json=payload)).status_code == 201

    second = await admin_client.post("/api/v1/categories", json=payload)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


async def test_categories_sort_by_sort_order_then_name(admin_client: AsyncClient) -> None:
    await admin_client.post(
        "/api/v1/categories", json={"slug": "z", "name": "Zebra", "sort_order": 0}
    )
    await admin_client.post(
        "/api/v1/categories", json={"slug": "a", "name": "Apple", "sort_order": 5}
    )

    names = [c["name"] for c in (await admin_client.get("/api/v1/categories")).json()]
    assert names == ["Zebra", "Apple"]


async def test_category_writes_require_admin(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/categories", json={"slug": "x", "name": "X"})
    assert resp.status_code == 401


async def test_deleting_a_category_keeps_its_topics(admin_client: AsyncClient) -> None:
    category = (
        await admin_client.post("/api/v1/categories", json={"slug": "travel", "name": "Travel"})
    ).json()
    topic = (
        await admin_client.post(
            "/api/v1/topics",
            json={"slug": "flights", "title": "Flights", "category_id": category["id"]},
        )
    ).json()

    assert (await admin_client.delete(f"/api/v1/categories/{category['id']}")).status_code == 204

    # The topic keeps working; it just loses its grouping. (The FK sets
    # `category_id` to NULL on Postgres; SQLite doesn't enforce FKs here, so the
    # test asserts only what holds on both — the topic is still there.)
    survivor = await admin_client.get(f"/api/v1/topics/{topic['id']}")
    assert survivor.status_code == 200
    assert survivor.json()["title"] == "Flights"


async def test_topic_with_unknown_category_returns_404(admin_client: AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/v1/topics",
        json={"slug": "orphan", "title": "Orphan", "category_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
