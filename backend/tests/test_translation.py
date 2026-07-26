import pytest
from httpx import AsyncClient


async def test_translate_returns_result(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep this a fast, deterministic unit test of the endpoint contract via the
    # zero-dependency stub. The real offline Argos engine is exercised separately
    # so unit tests never load heavy models or hit the network.
    monkeypatch.setattr("app.core.config.settings.translation_provider", "stub")
    resp = await client.post(
        "/api/v1/translate",
        json={"text": "Xin chào", "target_lang": "en"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_lang"] == "en"
    assert body["translated_text"]
    assert body["provider"] == "stub"


async def test_translate_requires_text(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/translate", json={"text": "", "target_lang": "en"})
    assert resp.status_code == 422
