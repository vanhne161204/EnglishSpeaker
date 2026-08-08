"""Speech-to-Text service (PRD §8.9).

Turns recorded audio into text. The default engine is **faster-whisper** — an
offline, open-source ASR model (CTranslate2), so transcription does NOT depend on
an LLM or external API. Falls back to a clearly-labelled stub when the package or
model is unavailable, so the demo runs with zero setup. Decoding/inference is
blocking CPU work, so it runs in a worker thread.
"""

import asyncio
import io
import logging
from typing import Any

from app.core.config import settings
from app.schemas.transcription import TranscriptionResult

logger = logging.getLogger(__name__)


class TranscriptionService:
    async def transcribe(
        self, audio: bytes, language: str | None = None
    ) -> TranscriptionResult:
        if not audio:
            return TranscriptionResult(text="", language=language, provider="noop")

        provider = settings.stt_provider.lower()

        if provider == "deepgram":
            result = await _deepgram_transcribe(audio, language)
            if result is not None:
                text, detected = result
                return TranscriptionResult(text=text, language=detected, provider="deepgram")

        elif provider in ("whisper", "faster_whisper", "auto"):
            result = await asyncio.to_thread(_whisper_transcribe, audio, language)
            if result is not None:
                text, detected = result
                return TranscriptionResult(text=text, language=detected, provider="whisper")

        return self._stub(language)

    def _stub(self, language: str | None) -> TranscriptionResult:
        return TranscriptionResult(
            text="[demo transcript — install faster-whisper to transcribe real speech]",
            language=language,
            provider="stub",
        )


async def _deepgram_transcribe(
    audio: bytes, language: str | None
) -> tuple[str, str | None] | None:
    """Transcribe via the Deepgram cloud API, or return ``None`` to fall back.

    Sends the raw audio to Deepgram's pre-recorded endpoint. Accurate and adds no
    CPU load to the server. Requires ``settings.deepgram_api_key``.
    """
    if not settings.deepgram_api_key:
        logger.warning("STT_PROVIDER=deepgram but DEEPGRAM_API_KEY is not set — falling back.")
        return None

    import httpx

    params = {
        "model": settings.deepgram_model,
        "smart_format": "true",  # punctuation, capitalization, numerals
        "language": language or "en",
    }
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        # Browser MediaRecorder produces WebM/Opus; Deepgram also auto-detects.
        "Content-Type": "audio/webm",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/listen",
                params=params,
                headers=headers,
                content=audio,
            )
            resp.raise_for_status()
            data = resp.json()
            alt = data["results"]["channels"][0]["alternatives"][0]
            return alt.get("transcript", "").strip(), language or "en"
    except Exception as exc:  # noqa: BLE001 — degrade to stub on any API/parse error
        logger.warning("Deepgram transcription failed: %s", exc)
        return None


# The model is expensive to load, so keep one instance for the process.
_model: Any = None


def _whisper_transcribe(audio: bytes, language: str | None) -> tuple[str, str | None] | None:
    """Transcribe audio bytes, or return ``None`` so the caller can fall back."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning(
            "faster-whisper not installed — Speech-to-Text falling back to stub. "
            "`pip install faster-whisper` to enable offline transcription."
        )
        return None

    try:
        global _model
        if _model is None:
            _model = WhisperModel(settings.stt_model, device="cpu", compute_type="int8")
        segments, info = _model.transcribe(io.BytesIO(audio), language=language)
        text = "".join(segment.text for segment in segments).strip()
        return text, getattr(info, "language", language)
    except Exception as exc:  # noqa: BLE001 — degrade to stub on any engine error
        logger.warning("Whisper transcription failed: %s", exc)
        return None
