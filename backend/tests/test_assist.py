from httpx import AsyncClient


async def test_improve_returns_suggestion(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/assist",
        json={"kind": "improve", "text": "i very like travel"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "improve"
    assert body["suggestion"]
    # Demo runs without an API key → clearly-labelled stub provider.
    assert body["provider"] in {"claude", "stub"}


async def test_improve_requires_text(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/assist", json={"kind": "improve", "text": "   "})
    assert resp.status_code == 422


async def test_reply_suggestion_without_text(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/assist",
        json={"kind": "reply", "context": "What did you do this weekend?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "reply"
    assert body["suggestion"]


async def test_improve_accepts_topic_for_grounding(admin_client: AsyncClient) -> None:
    # Create a topic + document so the coach has trusted content to ground on (RAG).
    topic = (
        await admin_client.post("/api/v1/topics", json={"slug": "travel", "title": "Travel"})
    ).json()
    await admin_client.post(
        "/api/v1/documents",
        json={
            "topic_id": topic["id"],
            "kind": "vocabulary",
            "title": "Words",
            "content": "layover",
        },
    )
    resp = await admin_client.post(
        "/api/v1/assist",
        json={"kind": "improve", "text": "i go to many country", "topic_id": topic["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["suggestion"]
