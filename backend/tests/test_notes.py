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


async def test_save_a_translation_pair(client: AsyncClient) -> None:
    """The in-room translator saves both halves plus their languages (PRD §8.10)."""
    created = await client.post(
        "/api/v1/notes",
        json={
            "original_text": "tôi thích du lịch",
            "translated_text": "I like traveling",
            "source_lang": "vi",
            "target_lang": "en",
            "source": "translation",
            "topic": "Travel",
        },
    )
    assert created.status_code == 201
    note = created.json()
    assert note["translated_text"] == "I like traveling"
    assert (note["source_lang"], note["target_lang"]) == ("vi", "en")
    # A translation is not a correction, so the "better version" stays empty.
    assert note["improved_text"] is None


async def test_a_translation_alone_is_enough_text(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/notes", json={"translated_text": "I like traveling", "target_lang": "en"}
    )
    assert resp.status_code == 201


async def test_translation_fields_are_editable(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/notes",
        json={"original_text": "xin chào", "translated_text": "hello", "source_lang": "vi"},
    )
    note_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/notes/{note_id}", json={"translated_text": "hi there", "target_lang": "en"}
    )
    assert updated.status_code == 200
    assert updated.json()["translated_text"] == "hi there"
    assert updated.json()["target_lang"] == "en"


async def test_correction_notes_have_no_translation_fields(client: AsyncClient) -> None:
    """Existing notes keep working — the new columns simply stay empty."""
    created = await client.post(
        "/api/v1/notes", json={"original_text": "i very like travel", "improved_text": "I love it."}
    )
    note = created.json()
    assert note["translated_text"] is None
    assert note["source_lang"] is None and note["target_lang"] is None
