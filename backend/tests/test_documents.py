import uuid

from httpx import AsyncClient


async def _make_topic(client: AsyncClient, slug: str = "travel-test") -> str:
    resp = await client.post("/api/v1/topics", json={"slug": slug, "title": "Travel Test"})
    return resp.json()["id"]


async def test_document_crud(admin_client: AsyncClient) -> None:
    topic_id = await _make_topic(admin_client)

    created = await admin_client.post(
        "/api/v1/documents",
        json={
            "topic_id": topic_id,
            "kind": "vocabulary",
            "title": "Words",
            "content": "itinerary, layover",
        },
    )
    assert created.status_code == 201
    doc = created.json()
    assert doc["kind"] == "vocabulary" and doc["topic_id"] == topic_id

    listed = await admin_client.get("/api/v1/documents", params={"topic_id": topic_id})
    assert listed.status_code == 200
    assert any(d["id"] == doc["id"] for d in listed.json())

    got = await admin_client.get(f"/api/v1/documents/{doc['id']}")
    assert got.status_code == 200 and got.json()["title"] == "Words"

    updated = await admin_client.patch(
        f"/api/v1/documents/{doc['id']}", json={"title": "Travel words"}
    )
    assert updated.status_code == 200 and updated.json()["title"] == "Travel words"

    deleted = await admin_client.delete(f"/api/v1/documents/{doc['id']}")
    assert deleted.status_code == 204
    assert (await admin_client.get(f"/api/v1/documents/{doc['id']}")).status_code == 404


async def test_create_document_unknown_topic_returns_404(admin_client: AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/v1/documents",
        json={"topic_id": str(uuid.uuid4()), "title": "x", "content": "y"},
    )
    assert resp.status_code == 404


async def test_document_requires_title_and_content(admin_client: AsyncClient) -> None:
    topic_id = await _make_topic(admin_client, slug="food-test")
    resp = await admin_client.post(
        "/api/v1/documents",
        json={"topic_id": topic_id, "title": "", "content": "y"},
    )
    assert resp.status_code == 422


async def test_list_documents_filters_by_topic(admin_client: AsyncClient) -> None:
    t1 = await _make_topic(admin_client, slug="t1")
    t2 = await _make_topic(admin_client, slug="t2")
    await admin_client.post(
        "/api/v1/documents", json={"topic_id": t1, "title": "A", "content": "a"}
    )
    await admin_client.post(
        "/api/v1/documents", json={"topic_id": t2, "title": "B", "content": "b"}
    )

    only_t1 = (await admin_client.get("/api/v1/documents", params={"topic_id": t1})).json()
    assert len(only_t1) == 1 and only_t1[0]["title"] == "A"
