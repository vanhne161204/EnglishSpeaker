from httpx import AsyncClient


async def test_list_rooms_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/rooms")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_rooms_mode_filter_validates(client: AsyncClient) -> None:
    ok = await client.get("/api/v1/rooms", params={"mode": "incognito"})
    assert ok.status_code == 200

    bad = await client.get("/api/v1/rooms", params={"mode": "nope"})
    assert bad.status_code == 422


async def test_list_rooms_kind_filter_validates(client: AsyncClient) -> None:
    ok = await client.get("/api/v1/rooms", params={"kind": "one_on_one"})
    assert ok.status_code == 200

    bad = await client.get("/api/v1/rooms", params={"kind": "duo"})
    assert bad.status_code == 422
