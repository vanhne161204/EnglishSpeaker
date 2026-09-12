"""The pronunciation port (Shadowing Phase 2, PRD §8.14; docs §18.15).

Takes the learner's audio and the sentence they were reading, and returns
phoneme-based scores. Unlike speech-to-text it is told the sentence first
("scripted" assessment), so it can say HOW a word was said, not just WHICH word
it heard — the thing a word match cannot do (docs/10_AI_Design.md §10.3.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.ai.errors import ProviderError


class NothingHeard(ProviderError):
    """The audio held no usable speech (silence or noise). Not worth retrying."""

    retryable = False


@dataclass(frozen=True, slots=True)
class AssessedWord:
    #: The word as the vendor lists it (lower case for Azure).
    word: str
    #: 0-100, or None when the vendor gave no score.
    accuracy: float | None
    #: The vendor's error type: "None", "Mispronunciation", "Omission", "Insertion".
    error: str


@dataclass(frozen=True, slots=True)
class PronunciationReport:
    accuracy: float | None
    fluency: float | None
    completeness: float | None
    #: None when the prosody add-on was not requested.
    prosody: float | None
    #: The vendor's own overall score. It counts names too, so we do not show it.
    overall: float | None
    #: What the vendor recognised. Biased toward the sentence in scripted mode.
    recognized: str
    words: list[AssessedWord]
    provider: str
    model: str


class PronunciationAssessor(Protocol):
    name: str
    model: str
    #: Whether prosody is requested — it is billed as an add-on.
    prosody: bool

    async def assess(self, wav_16k_mono: bytes, reference_text: str) -> PronunciationReport: ...
