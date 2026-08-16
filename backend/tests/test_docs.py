"""Topic documentation endpoints (PRD §8.2) — docs, sections, items."""

import uuid

from httpx import AsyncClient


async def make_topic(client: AsyncClient, slug: str = "travel-test") -> str:
    resp = await client.post("/api/v1/topics", json={"slug": slug, "title": "Travel Test"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def make_doc(client: AsyncClient, topic_id: str, status: str = "published") -> str:
    resp = await client.post(
        "/api/v1/docs", json={"topic_id": topic_id, "intro": "Read me first.", "status": status}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def make_section(client: AsyncClient, doc_id: str, type_: str, **extra: object) -> str:
    resp = await client.post(f"/api/v1/docs/{doc_id}/sections", json={"type": type_, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_doc_crud(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)

    created = await admin_client.post(
        "/api/v1/docs", json={"topic_id": topic_id, "title": "Travel", "status": "draft"}
    )
    assert created.status_code == 201
    doc = created.json()
    assert doc["topic_id"] == topic_id and doc["status"] == "draft"

    listed = await admin_client.get("/api/v1/docs", params={"topic_id": topic_id})
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()] == [doc["id"]]

    got = await admin_client.get(f"/api/v1/docs/{doc['id']}")
    assert got.status_code == 200 and got.json()["sections"] == []

    updated = await admin_client.patch(
        f"/api/v1/docs/{doc['id']}", json={"title": "World Travel", "status": "published"}
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "World Travel" and updated.json()["status"] == "published"

    deleted = await admin_client.delete(f"/api/v1/docs/{doc['id']}")
    assert deleted.status_code == 204
    assert (await admin_client.get(f"/api/v1/docs/{doc['id']}")).status_code == 404


async def test_create_doc_unknown_topic_returns_404(admin_client: AsyncClient) -> None:
    resp = await admin_client.post("/api/v1/docs", json={"topic_id": str(uuid.uuid4())})
    assert resp.status_code == 404


async def test_topic_has_at_most_one_doc(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    await make_doc(admin_client, topic_id)

    second = await admin_client.post("/api/v1/docs", json={"topic_id": topic_id})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


async def test_get_topic_doc_returns_the_full_tree(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    doc_id = await make_doc(admin_client, topic_id)

    vocab = await make_section(
        admin_client, doc_id, "vocabulary", title="Words", sort_order=1
    )
    questions = await make_section(
        admin_client, doc_id, "questions", title="Questions", sort_order=0
    )
    await admin_client.post(
        f"/api/v1/docs/sections/{vocab}/items",
        json={"term": "layover", "phonetic": "/ˈleɪoʊvər/", "meaning": "a wait between flights"},
    )
    question = (
        await admin_client.post(
            "/api/v1/questions", json={"section_id": questions, "text": "Where would you go?"}
        )
    ).json()
    await admin_client.post(
        f"/api/v1/questions/{question['id']}/answers",
        json={"template": "I would go to ___.", "example": "I would go to Japan."},
    )

    tree = (await admin_client.get(f"/api/v1/topics/{topic_id}/doc")).json()
    # Sections come back in `sort_order`, not creation order.
    assert [s["type"] for s in tree["sections"]] == ["questions", "vocabulary"]

    question_section, vocab_section = tree["sections"]
    assert vocab_section["items"][0]["term"] == "layover"
    assert question_section["questions"][0]["text"] == "Where would you go?"
    assert question_section["questions"][0]["answer_templates"][0]["example"] == (
        "I would go to Japan."
    )


async def test_get_topic_doc_404s_when_there_is_none(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    assert (await admin_client.get(f"/api/v1/topics/{topic_id}/doc")).status_code == 404
    assert (await admin_client.get(f"/api/v1/topics/{uuid.uuid4()}/doc")).status_code == 404


async def test_section_crud(admin_client: AsyncClient) -> None:
    doc_id = await make_doc(admin_client, await make_topic(admin_client))
    section_id = await make_section(admin_client, doc_id, "tips", title="Tips", body="Slow down.")

    updated = await admin_client.patch(
        f"/api/v1/docs/sections/{section_id}", json={"body": "Slow down and breathe."}
    )
    assert updated.status_code == 200 and updated.json()["body"] == "Slow down and breathe."

    assert (await admin_client.delete(f"/api/v1/docs/sections/{section_id}")).status_code == 204
    tree = (await admin_client.get(f"/api/v1/docs/{doc_id}")).json()
    assert tree["sections"] == []


async def test_deleting_a_doc_removes_its_whole_tree(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    doc_id = await make_doc(admin_client, topic_id)
    section_id = await make_section(admin_client, doc_id, "questions")
    question = (
        await admin_client.post(
            "/api/v1/questions", json={"section_id": section_id, "text": "Gone soon?"}
        )
    ).json()

    assert (await admin_client.delete(f"/api/v1/docs/{doc_id}")).status_code == 204

    # The section and its questions go with it.
    assert (
        await admin_client.patch(f"/api/v1/docs/sections/{section_id}", json={"title": "x"})
    ).status_code == 404
    assert (
        await admin_client.patch(f"/api/v1/questions/{question['id']}", json={"text": "x"})
    ).status_code == 404


async def test_item_crud(admin_client: AsyncClient) -> None:
    doc_id = await make_doc(admin_client, await make_topic(admin_client))
    section_id = await make_section(admin_client, doc_id, "phrases")

    created = await admin_client.post(
        f"/api/v1/docs/sections/{section_id}/items",
        json={"term": "I'm not a big fan of ___", "meaning": "a polite dislike"},
    )
    assert created.status_code == 201
    item = created.json()

    updated = await admin_client.patch(
        f"/api/v1/docs/items/{item['id']}", json={"example": "I'm not a big fan of coffee."}
    )
    assert updated.status_code == 200
    assert updated.json()["example"] == "I'm not a big fan of coffee."

    assert (await admin_client.delete(f"/api/v1/docs/items/{item['id']}")).status_code == 204
    assert (
        await admin_client.patch(f"/api/v1/docs/items/{item['id']}", json={"term": "x"})
    ).status_code == 404


async def test_items_rejected_in_a_questions_section(admin_client: AsyncClient) -> None:
    doc_id = await make_doc(admin_client, await make_topic(admin_client))
    section_id = await make_section(admin_client, doc_id, "questions")

    resp = await admin_client.post(
        f"/api/v1/docs/sections/{section_id}/items", json={"term": "layover"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


async def test_unknown_section_type_is_rejected(admin_client: AsyncClient) -> None:
    doc_id = await make_doc(admin_client, await make_topic(admin_client))
    resp = await admin_client.post(f"/api/v1/docs/{doc_id}/sections", json={"type": "recipes"})
    assert resp.status_code == 422


async def test_doc_writes_require_admin(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/docs", json={"topic_id": str(uuid.uuid4())})
    assert resp.status_code == 401
