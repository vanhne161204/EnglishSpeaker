"""Translation service for the in-room translator (PRD §8.10).

Owns *what to translate*, never *which engine*. Engine choice, fallback order and
failure handling live behind the ``Translator`` port
(docs/18_AI_Provider_Architecture.md §18.10), so the old
``if provider in ("google", "auto")`` chains inlined in this file are gone —
ordering is now configuration.

Engines available: Google (best Vietnamese quality), Argos (offline, private),
an LLM-backed translator, and a labelled stub. The chain always ends in the stub
so the translator degrades instead of failing.
"""

from __future__ import annotations

import logging

from app.ai.errors import ProviderError
from app.ai.translate_port import TranslateJob, Translator
from app.schemas.translation import TranslateRequest, TranslateResult

logger = logging.getLogger(__name__)


class TranslationService:
    def __init__(self, translator: Translator) -> None:
        self._translator = translator

    async def translate(self, payload: TranslateRequest) -> TranslateResult:
        text = payload.text.strip()
        if not text:
            return TranslateResult(
                translated_text="", target_lang=payload.target_lang, provider="noop"
            )

        job = TranslateJob(
            text=text,
            target_lang=payload.target_lang,
            source_lang=payload.source_lang,
        )
        try:
            result = await self._translator.translate(job)
        except ProviderError as exc:
            # The chain ends in a stub that cannot fail, so reaching here means
            # something unexpected. Degrade rather than 500 a live room.
            logger.warning("Translation failed entirely: %s", exc)
            return TranslateResult(
                translated_text=text, target_lang=payload.target_lang, provider="stub"
            )

        return TranslateResult(
            translated_text=result.text,
            target_lang=result.target_lang,
            provider=result.provider,
        )
