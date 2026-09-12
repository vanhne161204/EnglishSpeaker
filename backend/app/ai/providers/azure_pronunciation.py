"""Azure Pronunciation Assessment adapter (Shadowing Phase 2; docs §18.15).

REST API for short audio, scripted mode: the sentence goes in a base64
``Pronunciation-Assessment`` header, the audio (16 kHz mono 16-bit WAV, at most
30 s) in the body. Verified live on 2026-09-12 against a Central India resource
(scripts/check_azure_pronunciation.py): audio of "ship" scored against the text
"sheep" gave ``sheep`` accuracy 35 / Mispronunciation, while a native-like voice
scored 86-100 on the other words.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from app.ai.errors import (
    ProviderBadRequest,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.ai.pronunciation_port import (
    AssessedWord,
    NothingHeard,
    PronunciationAssessor,
    PronunciationReport,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

ASSESS_TIMEOUT_S = 20.0
MODEL = "pronunciation-assessment"


def _score(item: dict[str, Any], key: str) -> float | None:
    """A score from either response shape.

    The REST detailed format puts scores on the item itself (what Phase 0 saw);
    the SDK's JSON nests them under "PronunciationAssessment".
    """
    value = item.get(key)
    if value is None:
        value = (item.get("PronunciationAssessment") or {}).get(key)
    return float(value) if isinstance(value, int | float) else None


def _error_type(item: dict[str, Any]) -> str:
    value = item.get("ErrorType") or (item.get("PronunciationAssessment") or {}).get("ErrorType")
    return str(value or "None")


class AzurePronunciationAssessor:
    name = "azure"
    model = MODEL

    def __init__(
        self, key: str, region: str, endpoint: str | None = None, prosody: bool = True
    ) -> None:
        self._key = key
        self.prosody = prosody
        self._url = endpoint or (
            f"https://{region}.stt.speech.microsoft.com"
            "/speech/recognition/conversation/cognitiveservices/v1"
        )

    async def assess(self, wav_16k_mono: bytes, reference_text: str) -> PronunciationReport:
        parameters = {
            "ReferenceText": reference_text,
            "GradingSystem": "HundredMark",
            "Granularity": "Word",
            "Dimension": "Comprehensive",
            "EnableMiscue": "True",
        }
        if self.prosody:
            parameters["EnableProsodyAssessment"] = "True"
        headers = {
            "Ocp-Apim-Subscription-Key": self._key,
            "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
            "Accept": "application/json",
            "Pronunciation-Assessment": base64.b64encode(
                json.dumps(parameters).encode()
            ).decode(),
        }
        try:
            async with httpx.AsyncClient(timeout=ASSESS_TIMEOUT_S) as client:
                response = await client.post(
                    self._url,
                    params={"language": "en-US", "format": "detailed"},
                    headers=headers,
                    content=wav_16k_mono,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("azure", "pronunciation assessment timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("azure", str(exc)) from exc

        if response.status_code == 429:
            raise ProviderRateLimited("azure")
        if response.status_code >= 500:
            raise ProviderUnavailable("azure", f"HTTP {response.status_code}")
        if response.status_code != 200:
            # 401/403 = wrong key or region; 400 = audio or header problem.
            raise ProviderBadRequest("azure", f"HTTP {response.status_code}: {response.text[:200]}")

        body = response.json()
        if body.get("RecognitionStatus") != "Success":
            raise NothingHeard("azure", str(body.get("RecognitionStatus")))
        best: dict[str, Any] = (body.get("NBest") or [{}])[0]
        return PronunciationReport(
            accuracy=_score(best, "AccuracyScore"),
            fluency=_score(best, "FluencyScore"),
            completeness=_score(best, "CompletenessScore"),
            prosody=_score(best, "ProsodyScore") if self.prosody else None,
            overall=_score(best, "PronScore"),
            recognized=str(best.get("Display") or body.get("DisplayText") or ""),
            words=[
                AssessedWord(
                    word=str(word.get("Word", "")),
                    accuracy=_score(word, "AccuracyScore"),
                    error=_error_type(word),
                )
                for word in best.get("Words", [])
            ],
            provider=self.name,
            model=self.model,
        )


def build_assessor() -> PronunciationAssessor | None:
    """The configured assessor, or None when pronunciation checks are off.

    Off when ``AI_ENABLED`` is false (the kill switch, and the test suite) or when
    no ``AZURE_SPEECH_KEY`` is set.
    """
    if not settings.ai_enabled or not settings.azure_speech_key:
        return None
    return AzurePronunciationAssessor(
        settings.azure_speech_key,
        settings.azure_speech_region,
        settings.azure_speech_endpoint,
        prosody=settings.pronunciation_prosody,
    )
