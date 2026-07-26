import pytest
from httpx import AsyncClient


async def test_transcribe_returns_text(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the stub so the unit test never loads a heavy model or hits audio decoding.
    monkeypatch.setattr("app.core.config.settings.stt_provider", "stub")
    files = {"audio": ("clip.wav", b"\x00\x01\x02\x03", "audio/wav")}
    resp = await client.post("/api/v1/transcribe", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "stub"
    assert body["text"]


async def test_transcribe_requires_audio_file(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/transcribe")
    assert resp.status_code == 422
