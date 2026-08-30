"""The translation port (docs §18.2, §18.10).

Deliberately NOT the LLM port. Google Translate and Argos are not language
models: they take text and a language pair, and have no concept of a system
prompt, tokens, effort or structured output. Forcing them through
``LLMProvider`` would mean a parameter list where most fields are ``None``.

Three narrow ports stay honest; one wide port becomes a bag of nulls.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from app.ai.fallback import run_chain


@dataclass(frozen=True, slots=True)
class TranslateJob:
    text: str
    target_lang: str
    #: None means "detect it". Google can; Argos cannot and has to guess.
    source_lang: str | None = None


@dataclass(frozen=True, slots=True)
class Translation:
    text: str
    target_lang: str
    provider: str
    degraded: bool = False


@runtime_checkable
class Translator(Protocol):
    name: str

    async def translate(self, job: TranslateJob) -> Translation: ...


class TranslatorChain:
    """Try each engine in order; the first success wins."""

    def __init__(self, translators: Sequence[Translator]) -> None:
        if not translators:
            raise ValueError("a translator chain needs at least one engine")
        self._translators = tuple(translators)
        self.name = " -> ".join(t.name for t in self._translators)

    async def translate(self, job: TranslateJob) -> Translation:
        return await run_chain(
            self._translators,
            lambda translator: translator.translate(job),
            lambda result: replace(result, degraded=True),
            kind="translation",
        )
