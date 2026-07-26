from httpx import AsyncClient


async def test_match_one_creates_one_on_one_room(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/match/one", json={"mode": "normal", "topic": "Travel"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "one_on_one"
    assert body["capacity"] == 2
    assert body["mode"] == "normal"


async def test_random_match_returns_room_in_same_mode(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/match/random", json={"mode": "incognito"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "incognito"


async def test_match_one_carries_topic_and_level(client: AsyncClient) -> None:
    body = {"mode": "normal", "topic": "Travel", "level": "intermediate"}
    first = (await client.post("/api/v1/match/one", json=body)).json()
    assert first["topic"] == "Travel" and first["level"] == "intermediate"

    # A second identical request should reuse the same open room (find, not create).
    second = (await client.post("/api/v1/match/one", json=body)).json()
    assert second["id"] == first["id"]
