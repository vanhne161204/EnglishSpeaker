"""The text-to-speech port (Shadowing, PRD §8.14; docs §18.14).

Shadowing needs a model voice for every sentence the learner copies. Each clip is
made once and stored (`shadowing_clips`), so this port is called rarely: a
thousand sentences cost about $2 once, not on every play.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SpeechClip:
    #: A complete WAV file (RIFF header + 16-bit PCM), ready to serve as audio/wav.
    wav: bytes
    duration_ms: int
    provider: str
    model: str
    voice: str
    #: Billing units as the vendor reported them (0 when it reported none).
    input_tokens: int = 0
    output_tokens: int = 0


class Synthesizer(Protocol):
    name: str
    model: str
    voice: str

    async def synthesize(self, text: str) -> SpeechClip: ...
