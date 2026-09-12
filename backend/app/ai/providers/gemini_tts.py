"""Gemini text-to-speech adapter (Shadowing, PRD §8.14; docs §18.14).

Gemini returns raw 16-bit PCM. It is wrapped in a WAV header here, so the browser
can play the clip with a plain <audio> element and read its duration.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import wave
from functools import lru_cache
from typing import Any

from app.ai.errors import ProviderNotConfigured, ProviderTimeout, ProviderUnavailable
from app.ai.providers.gemini_live import translate_error
from app.ai.tts_port import SpeechClip, Synthesizer
from app.core.config import settings

logger = logging.getLogger(__name__)

SYNTH_TIMEOUT_S = 30.0
#: Gemini TTS answers at 24 kHz; used only if the MIME type does not say.
DEFAULT_SAMPLE_RATE = 24_000

#: Gemini TTS takes directions in plain language, before the text to read. This
#: keeps every clip at a calm pace a learner can copy.
STYLE = (
    "Read this sentence clearly, at a natural but slightly slow pace, "
    "in a friendly American English voice:"
)

_RATE = re.compile(r"rate=(\d+)")


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap mono 16-bit PCM in a WAV header."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm)
    return buffer.getvalue()


def _first_audio(response: Any) -> tuple[bytes | None, str | None]:
    for candidate in response.candidates or []:
        content = candidate.content
        for part in (content.parts if content else None) or []:
            blob = part.inline_data
            if blob and blob.data:
                return blob.data, blob.mime_type
    return None, None


class GeminiSynthesizer:
    name = "gemini"

    def __init__(self, api_key: str, model: str, voice: str) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise ProviderNotConfigured("gemini", "google-genai is not installed") from exc
        self.model = model
        self.voice = voice
        self._client = genai.Client(api_key=api_key)

    async def synthesize(self, text: str) -> SpeechClip:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
                )
            ),
            # No tools here. Turning automatic function calling off also stops the
            # SDK logging a warning on every call.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model, contents=f"{STYLE} {text}", config=config
                ),
                timeout=SYNTH_TIMEOUT_S,
            )
        except TimeoutError as exc:
            raise ProviderTimeout("gemini", "speech generation timed out") from exc
        except errors.APIError as exc:
            raise translate_error(exc) from exc
        except Exception as exc:  # noqa: BLE001 — connection errors from the HTTP client
            raise ProviderUnavailable("gemini", str(exc)) from exc

        pcm, mime = _first_audio(response)
        if not pcm:
            raise ProviderUnavailable("gemini", "no audio in the response")
        found = _RATE.search(mime or "")
        rate = int(found.group(1)) if found else DEFAULT_SAMPLE_RATE
        usage = response.usage_metadata
        return SpeechClip(
            wav=pcm_to_wav(pcm, rate),
            duration_ms=round(len(pcm) / 2 / rate * 1000),
            provider=self.name,
            model=self.model,
            voice=self.voice,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        )


@lru_cache(maxsize=4)
def _synthesizer_for(api_key: str, model: str, voice: str) -> GeminiSynthesizer:
    # One client per key, model and voice, reused across requests.
    return GeminiSynthesizer(api_key, model, voice)


def build_synthesizer() -> Synthesizer | None:
    """The configured synthesizer, or None when model voices are off.

    Off when ``AI_ENABLED`` is false (the kill switch, and the test suite) or when
    no ``GEMINI_API_KEY`` is set. The browser's own voice is used then.
    """
    if not settings.ai_enabled or not settings.gemini_api_key:
        return None
    try:
        return _synthesizer_for(
            settings.gemini_api_key, settings.shadowing_tts_model, settings.shadowing_tts_voice
        )
    except ProviderNotConfigured:
        logger.warning("GEMINI_API_KEY is set but google-genai is not installed — TTS off.")
        return None
