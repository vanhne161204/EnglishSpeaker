"""The one-call question/answer editor (PRD §8.1).

Authoring through the doc tree takes four calls; these endpoints do it in one and
build the missing scaffolding themselves.
"""

import uuid

from httpx import AsyncClient

from tests.test_docs import make_topic


async def save(client: AsyncClient, topic_id: str, items: list[dict[str, str | None]]):
    return await client.put(f"/api/v1/topics/{topic_id}/questions", json={"items": items})


async def test_saving_questions_builds_the_whole_tree(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)

    resp = await save(
        admin_client,
        topic_id,
        [
            {"text": "What is your favourite food?", "answer": "My favourite food is pizza."},
            {"text": "Do you like cooking?", "answer": "Yes, I cook every weekend."},
        ],
    )
    assert resp.status_code == 200, resp.text
    pairs = resp.json()
    assert [p["text"] for p in pairs] == [
        "What is your favourite food?",
        "Do you like cooking?",
    ]
    assert pairs[0]["answer"] == "My favourite food is pizza."
    assert [p["sort_order"] for p in pairs] == [0, 1]

    # The doc and its `questions` section were created automatically...
    doc = (await admin_client.get(f"/api/v1/topics/{topic_id}/doc")).json()
    assert doc["status"] == "published"
    assert [s["type"] for s in doc["sections"]] == ["questions"]
    assert len(doc["sections"][0]["questions"]) == 2

    # ...and each answer became one answer template on its question.
    first = doc["sections"][0]["questions"][0]
    assert first["answer_templates"][0]["template"] == "My favourite food is pizza."


async def test_saving_publishes_so_learners_see_the_questions(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    await save(admin_client, topic_id, [{"text": "Ready?", "answer": "Yes."}])

    # The Warm-up feed only serves published docs — saving must reach it.
    feed = (await admin_client.get("/api/v1/questions", params={"topic_id": topic_id})).json()
    assert [q["text"] for q in feed] == ["Ready?"]


async def test_saving_again_replaces_the_previous_list(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    await save(
        admin_client,
        topic_id,
        [{"text": "Old one", "answer": "Old answer"}, {"text": "Old two", "answer": None}],
    )

    resp = await save(admin_client, topic_id, [{"text": "New only", "answer": "New answer"}])
    assert resp.status_code == 200
    assert [p["text"] for p in resp.json()] == ["New only"]

    # The replaced questions are gone from the tree, not merely hidden.
    doc = (await admin_client.get(f"/api/v1/topics/{topic_id}/doc")).json()
    assert len(doc["sections"][0]["questions"]) == 1


async def test_reusing_the_existing_questions_section(admin_client: AsyncClient) -> None:
    """A second save must not pile up duplicate `questions` sections."""
    topic_id = await make_topic(admin_client)
    await save(admin_client, topic_id, [{"text": "One", "answer": "A"}])
    await save(admin_client, topic_id, [{"text": "Two", "answer": "B"}])

    doc = (await admin_client.get(f"/api/v1/topics/{topic_id}/doc")).json()
    assert [s["type"] for s in doc["sections"]] == ["questions"]


async def test_an_answer_is_optional(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    resp = await save(admin_client, topic_id, [{"text": "No answer yet", "answer": "   "}])
    assert resp.status_code == 200
    assert resp.json()[0]["answer"] is None

    doc = (await admin_client.get(f"/api/v1/topics/{topic_id}/doc")).json()
    assert doc["sections"][0]["questions"][0]["answer_templates"] == []


async def test_listing_pairs_includes_a_draft_doc(admin_client: AsyncClient) -> None:
    """The editor must load what is stored, or the next save would wipe it."""
    topic_id = await make_topic(admin_client)
    await save(admin_client, topic_id, [{"text": "Hidden", "answer": "Still here"}])

    doc = (await admin_client.get(f"/api/v1/topics/{topic_id}/doc")).json()
    await admin_client.patch(f"/api/v1/docs/{doc['id']}", json={"status": "draft"})

    pairs = (await admin_client.get(f"/api/v1/topics/{topic_id}/questions")).json()
    assert [p["text"] for p in pairs] == ["Hidden"]
    # The learner-facing feed still hides it, because the doc is a draft.
    assert (await admin_client.get("/api/v1/questions", params={"topic_id": topic_id})).json() == []


async def test_empty_list_clears_every_question(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    await save(admin_client, topic_id, [{"text": "Bye", "answer": "Gone"}])

    assert (await save(admin_client, topic_id, [])).json() == []
    assert (await admin_client.get(f"/api/v1/topics/{topic_id}/questions")).json() == []


async def test_pairs_for_a_topic_with_no_doc_is_empty_not_404(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    resp = await admin_client.get(f"/api/v1/topics/{topic_id}/questions")
    assert resp.status_code == 200 and resp.json() == []


async def test_unknown_topic_returns_404(admin_client: AsyncClient) -> None:
    assert (await admin_client.get(f"/api/v1/topics/{uuid.uuid4()}/questions")).status_code == 404
    assert (await save(admin_client, str(uuid.uuid4()), [])).status_code == 404


async def test_blank_question_text_is_rejected(admin_client: AsyncClient) -> None:
    topic_id = await make_topic(admin_client)
    assert (await save(admin_client, topic_id, [{"text": "", "answer": "x"}])).status_code == 422


async def test_saving_questions_requires_admin(client: AsyncClient) -> None:
    resp = await client.put(
        f"/api/v1/topics/{uuid.uuid4()}/questions", json={"items": []}
    )
    assert resp.status_code == 401


async def test_existing_sections_are_left_alone(admin_client: AsyncClient) -> None:
    """Saving questions must not disturb vocabulary or tips already on the doc."""
    topic_id = await make_topic(admin_client)
    doc = (
        await admin_client.post(
            "/api/v1/docs", json={"topic_id": topic_id, "status": "published"}
        )
    ).json()
    await admin_client.post(
        f"/api/v1/docs/{doc['id']}/sections",
        json={"type": "vocabulary", "title": "Words", "sort_order": 0},
    )

    await save(admin_client, topic_id, [{"text": "Q", "answer": "A"}])

    tree = (await admin_client.get(f"/api/v1/topics/{topic_id}/doc")).json()
    assert [s["type"] for s in tree["sections"]] == ["vocabulary", "questions"]
