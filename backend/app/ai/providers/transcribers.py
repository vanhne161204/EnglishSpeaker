"""Speech-to-text engines behind the ``Transcriber`` port (docs §18.10).

* ``FasterWhisperTranscriber`` — offline, open source, no API key, no per-minute
  cost. CPU-bound, so it runs in a worker thread; heavy for a t3.small under load
  (docs/10_AI_Design.md §8.9).
* ``DeepgramTranscriber``      — cloud API. Accurate, no server load, needs a key,
  and bills per audio **minute** rather than per token.
* ``StubTranscriber``          — labelled placeholder so the demo runs with zero
  setup.

Note that the browser's own Web Speech API is the primary path in the product
plan and never reaches this code — these engines serve the upload fallback for
browsers without it.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from app.ai.errors import ProviderBadRequest, ProviderTimeout, ProviderUnavailable
from app.ai.stt_port import Transcript

logger = logging.getLogger(__name__)

_DEEPGRAM_TIMEOUT_S = 30.0


class FasterWhisperTranscriber:
    name = "whisper"

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        # Loading the model is expensive; keep one per instance for the process.
        self._model: Any = None

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        result = await asyncio.to_thread(self._run, audio, language)
        if result is None:
            raise ProviderUnavailable(self.name, "faster-whisper unavailable")
        text, detected, duration = result
        return Transcript(
            text=text, language=detected, provider=self.name, duration_s=duration
        )

    def _run(
        self, audio: bytes, language: str | None
    ) -> tuple[str, str | None, float | None] | None:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.warning(
                "faster-whisper not installed — `pip install faster-whisper` to enable "
                "offline transcription."
            )
            return None

        try:
            if self._model is None:
                self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
            segments, info = self._model.transcribe(io.BytesIO(audio), language=language)
            text = "".join(segment.text for segment in segments).strip()
            return text, getattr(info, "language", language), getattr(info, "duration", None)
        except Exception as exc:  # noqa: BLE001 — let the chain try the next engine
            logger.warning("Whisper transcription failed: %s", exc)
            return None


class DeepgramTranscriber:
    name = "deepgram"

    def __init__(self, api_key: str, model: str = "nova-2") -> None:
        self._api_key = api_key
        self._model = model

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        import httpx

        params = {
            "model": self._model,
            "smart_format": "true",  # punctuation, capitalization, numerals
            "language": language or "en",
        }
        headers = {
            "Authorization": f"Token {self._api_key}",
            # Browser MediaRecorder produces WebM/Opus; Deepgram also auto-detects.
            "Content-Type": "audio/webm",
        }
        try:
            async with httpx.AsyncClient(timeout=_DEEPGRAM_TIMEOUT_S) as client:
                resp = await client.post(
                    "https://api.deepgram.com/v1/listen",
                    params=params,
                    headers=headers,
                    content=audio,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(self.name) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise ProviderUnavailable(self.name, str(exc)) from exc
            raise ProviderBadRequest(self.name, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — network/parse: try the next engine
            raise ProviderUnavailable(self.name, str(exc)) from exc

        try:
            alternative = data["results"]["channels"][0]["alternatives"][0]
        except (KeyError, IndexError) as exc:
            raise ProviderUnavailable(self.name, "unexpected response shape") from exc

        return Transcript(
            text=(alternative.get("transcript") or "").strip(),
            language=language or "en",
            provider=self.name,
            duration_s=(data.get("metadata") or {}).get("duration"),
            confidence=alternative.get("confidence"),
        )


class StubTranscriber:
    """Never fails. Last link in the chain so the demo runs with zero setup."""

    name = "stub"

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        return Transcript(
            text="[demo transcript — set an STT engine to transcribe real speech]",
            language=language,
            provider=self.name,
            degraded=True,
        )
