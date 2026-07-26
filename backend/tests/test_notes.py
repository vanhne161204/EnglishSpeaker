import uuid

from httpx import AsyncClient


async def test_create_and_list_note(client: AsyncClient) -> None:
    payload = {
        "original_text": "I very like travel.",
        "improved_text": "I really enjoy travelling.",
        "source": "ai",
        "topic": "Travel",
    }
    created = await client.post("/api/v1/notes", json=payload)
    assert created.status_code == 201
    assert created.json()["improved_text"] == "I really enjoy travelling."

    listed = await client.get("/api/v1/notes")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_note_requires_some_text(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/notes", json={"source": "self"})
    assert resp.status_code == 422


async def test_note_update_and_delete(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/notes", json={"original_text": "i very like travel", "source": "self"}
    )
    note_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/notes/{note_id}",
        json={"improved_text": "I really enjoy travelling.", "topic": "Travel"},
    )
    assert updated.status_code == 200
    assert updated.json()["improved_text"] == "I really enjoy travelling."
    assert updated.json()["topic"] == "Travel"

    deleted = await client.delete(f"/api/v1/notes/{note_id}")
    assert deleted.status_code == 204
    assert (await client.delete(f"/api/v1/notes/{note_id}")).status_code == 404


async def test_update_unknown_note_returns_404(client: AsyncClient) -> None:
    resp = await client.patch(f"/api/v1/notes/{uuid.uuid4()}", json={"topic": "x"})
    assert resp.status_code == 404
