"""Speech-to-Text service (PRD §8.9).

Owns *what to transcribe*, never *which engine*. Engine choice and fallback live
behind the ``Transcriber`` port (docs/18_AI_Provider_Architecture.md §18.10):
offline faster-whisper, the Deepgram cloud API, or a labelled stub.

Note this is the **fallback** path. The product plan runs speech-to-text in the
browser via the Web Speech API, which costs nothing and never reaches the server;
these engines serve browsers without it and the push-to-talk upload.
"""

from __future__ import annotations

import logging

from app.ai.errors import ProviderError
from app.ai.stt_port import Transcriber
from app.schemas.transcription import TranscriptionResult

logger = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(self, transcriber: Transcriber) -> None:
        self._transcriber = transcriber

    async def transcribe(
        self, audio: bytes, language: str | None = None
    ) -> TranscriptionResult:
        if not audio:
            return TranscriptionResult(text="", language=language, provider="noop")

        try:
            transcript = await self._transcriber.transcribe(audio, language)
        except ProviderError as exc:
            # The chain ends in a stub that cannot fail, so reaching here is
            # unexpected. Degrade rather than fail the learner's recording.
            logger.warning("Transcription failed entirely: %s", exc)
            return TranscriptionResult(text="", language=language, provider="stub")

        return TranscriptionResult(
            text=transcript.text,
            language=transcript.language,
            provider=transcript.provider,
        )
