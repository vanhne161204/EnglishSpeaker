import uuid

from httpx import AsyncClient


async def test_create_and_list_topic(admin_client: AsyncClient) -> None:
    payload = {"slug": "test-topic", "title": "Test Topic", "level": "beginner"}

    created = await admin_client.post("/api/v1/topics", json=payload)
    assert created.status_code == 201
    assert created.json()["slug"] == "test-topic"

    listed = await admin_client.get("/api/v1/topics")
    assert listed.status_code == 200
    slugs = [topic["slug"] for topic in listed.json()]
    assert "test-topic" in slugs


async def test_duplicate_slug_conflicts(admin_client: AsyncClient) -> None:
    payload = {"slug": "dup", "title": "Dup"}
    first = await admin_client.post("/api/v1/topics", json=payload)
    assert first.status_code == 201

    second = await admin_client.post("/api/v1/topics", json=payload)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


async def test_topic_get_update_delete(admin_client: AsyncClient) -> None:
    created = await admin_client.post("/api/v1/topics", json={"slug": "travel", "title": "Travel"})
    topic_id = created.json()["id"]

    got = await admin_client.get(f"/api/v1/topics/{topic_id}")
    assert got.status_code == 200 and got.json()["title"] == "Travel"

    updated = await admin_client.patch(
        f"/api/v1/topics/{topic_id}", json={"title": "World Travel", "level": "intermediate"}
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "World Travel"
    assert updated.json()["level"] == "intermediate"

    deleted = await admin_client.delete(f"/api/v1/topics/{topic_id}")
    assert deleted.status_code == 204
    assert (await admin_client.get(f"/api/v1/topics/{topic_id}")).status_code == 404


async def test_update_unknown_topic_returns_404(admin_client: AsyncClient) -> None:
    resp = await admin_client.patch(f"/api/v1/topics/{uuid.uuid4()}", json={"title": "x"})
    assert resp.status_code == 404
