"""Question + answer-template endpoints (PRD §8.2), and the flat Warm-up feed (§8.12)."""

import uuid

from httpx import AsyncClient

from tests.test_docs import make_doc, make_section, make_topic


async def test_question_crud(admin_client: AsyncClient) -> None:
    doc_id = await make_doc(admin_client, await make_topic(admin_client))
    section_id = await make_section(admin_client, doc_id, "questions")

    created = await admin_client.post(
        "/api/v1/questions",
        json={"section_id": section_id, "text": "What is your favourite food?"},
    )
    assert created.status_code == 201
    question = created.json()
    assert question["answer_templates"] == []

    updated = await admin_client.patch(
        f"/api/v1/questions/{question['id']}", json={"translation": "Món ăn yêu thích của bạn?"}
    )
    assert updated.status_code == 200
    assert updated.json()["translation"] == "Món ăn yêu thích của bạn?"

    assert (await admin_client.delete(f"/api/v1/questions/{question['id']}")).status_code == 204
    assert (
        await admin_client.patch(f"/api/v1/questions/{question['id']}", json={"text": "x"})
    ).status_code == 404


async def test_questions_rejected_outside_a_questions_section(admin_client: AsyncClient) -> None:
    doc_id = await make_doc(admin_client, await make_topic(admin_client))
    section_id = await make_section(admin_client, doc_id, "vocabulary")

    resp = await admin_client.post(
        "/api/v1/questions", json={"section_id": section_id, "text": "Nope?"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


async def test_answer_template_crud(admin_client: AsyncClient) -> None:
    doc_id = await make_doc(admin_client, await make_topic(admin_client))
    section_id = await make_section(admin_client, doc_id, "questions")
    question = (
        await admin_client.post(
            "/api/v1/questions",
            json={"section_id": section_id, "text": "What is your favourite food?"},
        )
    ).json()

    created = await admin_client.post(
        f"/api/v1/questions/{question['id']}/answers",
        json={"template": "My favourite food is ___.", "example": "My favourite food is pizza."},
    )
    assert created.status_code == 201
    answer = created.json()
    assert answer["question_id"] == question["id"]

    updated = await admin_client.patch(
        f"/api/v1/questions/answers/{answer['id']}", json={"example": "My favourite food is pho."}
    )
    assert updated.status_code == 200
    assert updated.json()["example"] == "My favourite food is pho."

    assert (
        await admin_client.delete(f"/api/v1/questions/answers/{answer['id']}")
    ).status_code == 204
    assert (
        await admin_client.patch(f"/api/v1/questions/answers/{answer['id']}", json={"example": "x"})
    ).status_code == 404


async def test_answers_on_unknown_question_return_404(admin_client: AsyncClient) -> None:
    resp = await admin_client.post(
        f"/api/v1/questions/{uuid.uuid4()}/answers", json={"template": "___"}
    )
    assert resp.status_code == 404


async def test_warmup_feed_lists_questions_with_their_topic(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client, slug="food")
    doc_id = await make_doc(admin_client, topic_id)
    section_id = await make_section(admin_client, doc_id, "questions")
    await admin_client.post(
        "/api/v1/questions",
        json={"section_id": section_id, "text": "Second", "sort_order": 1},
    )
    await admin_client.post(
        "/api/v1/questions",
        json={"section_id": section_id, "text": "First", "sort_order": 0},
    )

    feed = (await admin_client.get("/api/v1/questions")).json()
    assert [q["text"] for q in feed] == ["First", "Second"]
    assert all(q["topic_id"] == topic_id and q["topic_title"] == "Travel Test" for q in feed)


async def test_warmup_feed_filters_by_topic(admin_client: AsyncClient) -> None:
    topic_ids = {}
    for slug, text in (("a", "From A"), ("b", "From B")):
        topic_ids[slug] = await make_topic(admin_client, slug=slug)
        doc_id = await make_doc(admin_client, topic_ids[slug])
        section_id = await make_section(admin_client, doc_id, "questions")
        await admin_client.post("/api/v1/questions", json={"section_id": section_id, "text": text})

    only_a = (
        await admin_client.get("/api/v1/questions", params={"topic_id": topic_ids["a"]})
    ).json()
    assert [q["text"] for q in only_a] == ["From A"]


async def test_warmup_feed_skips_unpublished_docs(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    doc_id = await make_doc(admin_client, topic_id, status="draft")
    section_id = await make_section(admin_client, doc_id, "questions")
    await admin_client.post("/api/v1/questions", json={"section_id": section_id, "text": "Hidden"})

    assert (await admin_client.get("/api/v1/questions")).json() == []

    # Publishing the doc makes its questions visible to learners.
    await admin_client.patch(f"/api/v1/docs/{doc_id}", json={"status": "published"})
    assert [q["text"] for q in (await admin_client.get("/api/v1/questions")).json()] == ["Hidden"]


async def test_warmup_feed_includes_answer_templates(admin_client: AsyncClient) -> None:
    doc_id = await make_doc(admin_client, await make_topic(admin_client))
    section_id = await make_section(admin_client, doc_id, "questions")
    question = (
        await admin_client.post(
            "/api/v1/questions", json={"section_id": section_id, "text": "Tell me about you."}
        )
    ).json()
    await admin_client.post(
        f"/api/v1/questions/{question['id']}/answers", json={"template": "I'm a ___."}
    )

    feed = (await admin_client.get("/api/v1/questions")).json()
    assert feed[0]["answer_templates"][0]["template"] == "I'm a ___."


async def test_question_writes_require_admin(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/questions", json={"section_id": str(uuid.uuid4()), "text": "x"}
    )
    assert resp.status_code == 401
