"""The speech-to-text port (docs §18.2, §18.10).

Separate from the LLM port for a concrete reason: this one takes **audio bytes**,
which no Claude or GPT model accepts. That is not a detail to paper over with an
optional field — it is why pronunciation cannot be scored today
(docs/10_AI_Design.md §10.3.11).

Billing differs too. Deepgram charges per audio minute, not per token, so
``duration_s`` is what its cost is computed from. Do not force per-token pricing
onto an engine that does not bill that way.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from app.ai.fallback import run_chain


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    #: Detected or requested language code, when the engine reports one.
    language: str | None
    provider: str
    #: Audio length, when known — the billing unit for per-minute engines, and
    #: the input to the fluency metrics in docs/10_AI_Design.md §10.3.8.
    duration_s: float | None = None
    #: Engine confidence 0-1, when reported. Stored per segment so a learner's
    #: repeatedly-misheard words become a pronunciation hint list (§10.3.11).
    confidence: float | None = None
    degraded: bool = False


@runtime_checkable
class Transcriber(Protocol):
    name: str

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript: ...


class TranscriberChain:
    """Try each engine in order; the first success wins."""

    def __init__(self, transcribers: Sequence[Transcriber]) -> None:
        if not transcribers:
            raise ValueError("a transcriber chain needs at least one engine")
        self._transcribers = tuple(transcribers)
        self.name = " -> ".join(t.name for t in self._transcribers)

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        return await run_chain(
            self._transcribers,
            lambda transcriber: transcriber.transcribe(audio, language),
            lambda result: replace(result, degraded=True),
            kind="speech-to-text",
        )
