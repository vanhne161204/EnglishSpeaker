"""Speech-to-Text (transcription) response schema (PRD §8.9)."""

from pydantic import BaseModel


class TranscriptionResult(BaseModel):
    text: str
    # Detected (or requested) language code, when known.
    language: str | None = None
    # "whisper" when powered by faster-whisper, "stub" in zero-config demo mode.
    provider: str
