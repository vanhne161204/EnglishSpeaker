"""Translation service for the in-room translator.

The default engine is **Argos Translate** — a fully offline, open-source neural MT
library (CTranslate2 + SentencePiece). Translation therefore does NOT depend on any
LLM or external API: no key, no network at translate time, private by default.

Design:
- A provider abstraction (``TRANSLATION_PROVIDER``) keeps the engine swappable —
  ``argos`` (default), ``claude`` (opt-in, needs a key), or ``stub``.
- A clearly-labelled stub fallback means the demo still runs with zero setup even
  when the Argos package or a language model is not installed.
- Argos is CPU-bound and blocking, so it runs in a worker thread to keep the async
  event loop responsive.
"""

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.schemas.translation import TranslateRequest, TranslateResult

logger = logging.getLogger(__name__)

# Friendly names for the (LLM) providers' prompts and the stub label.
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "vi": "Vietnamese",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
}

# The app's primary pair, used to guess the source language when a caller omits it
# (Argos needs an explicit source — it has no built-in language detection).
_DEFAULT_PAIR = ("en", "vi")


class TranslationService:
    async def translate(self, payload: TranslateRequest) -> TranslateResult:
        text = payload.text.strip()
        if not text:
            return TranslateResult(
                translated_text="", target_lang=payload.target_lang, provider="noop"
            )

        provider = settings.translation_provider.lower()

        if provider in ("google", "auto"):
            result = await self._translate_with_google(text, payload)
            if result is not None:
                return result

        if provider in ("argos", "auto"):
            result = await self._translate_with_argos(text, payload)
            if result is not None:
                return result

        if provider in ("claude", "auto") and settings.anthropic_api_key:
            try:
                return await self._translate_with_claude(text, payload)
            except Exception as exc:  # noqa: BLE001 — never fail the call; degrade to stub
                logger.warning("Claude translation failed, falling back to stub: %s", exc)

        return self._stub(text, payload.target_lang)

    async def _translate_with_argos(
        self, text: str, payload: TranslateRequest
    ) -> TranslateResult | None:
        source = (payload.source_lang or self._guess_source(payload.target_lang)).lower()
        target = payload.target_lang.lower()
        if source == target:
            return TranslateResult(
                translated_text=text, target_lang=payload.target_lang, provider="argos"
            )

        # Argos is blocking CPU work — keep it off the event loop.
        translated = await asyncio.to_thread(_argos_translate, text, source, target)
        if translated is None:
            return None
        return TranslateResult(
            translated_text=translated, target_lang=payload.target_lang, provider="argos"
        )

    @staticmethod
    def _guess_source(target_lang: str) -> str:
        first, second = _DEFAULT_PAIR
        return first if target_lang.lower() != first else second

    async def _translate_with_google(
        self, text: str, payload: TranslateRequest
    ) -> TranslateResult | None:
        # Google auto-detects the source, so an omitted source_lang is fine here.
        source = (payload.source_lang or "auto").lower()
        target = payload.target_lang.lower()
        if source != "auto" and source == target:
            return TranslateResult(
                translated_text=text, target_lang=payload.target_lang, provider="google"
            )
        try:
            if settings.google_translate_api_key:
                translated = await _google_official(
                    text, source, target, settings.google_translate_api_key
                )
            else:
                translated = await _google_free(text, source, target)
        except Exception as exc:  # noqa: BLE001 — never fail the call; degrade to stub
            logger.warning("Google translation failed, falling back: %s", exc)
            return None
        if not translated:
            return None
        return TranslateResult(
            translated_text=translated, target_lang=payload.target_lang, provider="google"
        )

    async def _translate_with_claude(self, text: str, payload: TranslateRequest) -> TranslateResult:
        # Imported lazily so the demo runs without the SDK installed.
        from anthropic import AsyncAnthropic

        target_name = LANGUAGE_NAMES.get(payload.target_lang, payload.target_lang)
        source_clause = ""
        if payload.source_lang:
            source_name = LANGUAGE_NAMES.get(payload.source_lang, payload.source_lang)
            source_clause = f" The text is in {source_name}."

        system = (
            f"You are a translation engine for a language-learning app. "
            f"Translate the user's message into {target_name}.{source_clause} "
            "Reply with ONLY the translation — no quotes, no explanations, no notes."
        )

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.translation_model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": text}],
        )
        translated = "".join(
            block.text for block in message.content if block.type == "text"
        ).strip()
        return TranslateResult(
            translated_text=translated,
            target_lang=payload.target_lang,
            provider="claude",
        )

    def _stub(self, text: str, target_lang: str) -> TranslateResult:
        target_name = LANGUAGE_NAMES.get(target_lang, target_lang)
        return TranslateResult(
            translated_text=f"[demo → {target_name}] {text}",
            target_lang=target_lang,
            provider="stub",
        )


_argos_logging_silenced = False


def _silence_argos_logging() -> None:
    """Quieten Argos/Stanza, which log every token batch at INFO.

    Must run *after* argostranslate is imported: the library raises its own
    loggers to INFO on import, so configuring them earlier has no effect.
    """
    global _argos_logging_silenced
    if _argos_logging_silenced:
        return
    for name in ("argostranslate", "argostranslate.utils", "stanza"):
        logging.getLogger(name).setLevel(logging.WARNING)
    _argos_logging_silenced = True


async def _google_free(text: str, source: str, target: str) -> str:
    """Translate via Google's free public endpoint (no key; unofficial)."""
    import httpx

    params = {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://translate.googleapis.com/translate_a/single", params=params
        )
        resp.raise_for_status()
        data = resp.json()
    # data[0] is a list of [translatedChunk, originalChunk, ...]; join the chunks.
    segments = data[0] or []
    return "".join(seg[0] for seg in segments if seg and seg[0])


async def _google_official(text: str, source: str, target: str, api_key: str) -> str:
    """Translate via the official Google Cloud Translation API (v2, key-based)."""
    import httpx

    body: dict[str, str] = {"q": text, "target": target, "format": "text"}
    if source != "auto":
        body["source"] = source
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://translation.googleapis.com/language/translate/v2",
            params={"key": api_key},
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
    return str(data["data"]["translations"][0]["translatedText"])


def _argos_translate(text: str, from_code: str, to_code: str) -> str | None:
    """Translate with Argos, or return ``None`` so the caller can fall back.

    Runs in a worker thread. Returns ``None`` (never raises) when the package or
    the required language model is unavailable, so translation degrades gracefully.
    """
    try:
        import argostranslate.translate as translate_mod
    except ImportError:
        logger.warning(
            "argostranslate not installed — falling back to stub. "
            "`pip install argostranslate` to enable offline translation."
        )
        return None

    _silence_argos_logging()

    try:
        # Check the translation *direction*, not just the languages: installing
        # en->vi creates both language objects but only the en->vi model, so a
        # vi->en request must still trigger its own download.
        translation = _installed_translation(translate_mod, from_code, to_code)
        if translation is None and settings.argos_auto_download:
            _install_pair(from_code, to_code)
            translation = _installed_translation(translate_mod, from_code, to_code)

        if translation is None:
            logger.warning("No Argos model installed for %s->%s", from_code, to_code)
            return None

        return str(translation.translate(text))
    except Exception as exc:  # noqa: BLE001 — degrade to stub on any engine error
        logger.warning("Argos translation failed: %s", exc)
        return None


def _installed_translation(translate_mod: Any, from_code: str, to_code: str) -> Any:
    by_code = {lang.code: lang for lang in translate_mod.get_installed_languages()}
    from_lang, to_lang = by_code.get(from_code), by_code.get(to_code)
    if from_lang is None or to_lang is None:
        return None
    return from_lang.get_translation(to_lang)


def _install_pair(from_code: str, to_code: str) -> None:
    import argostranslate.package as package_mod

    package_mod.update_package_index()
    available = package_mod.get_available_packages()
    package = next(
        (p for p in available if p.from_code == from_code and p.to_code == to_code), None
    )
    if package is None:
        logger.warning("No downloadable Argos package for %s->%s", from_code, to_code)
        return
    logger.info("Downloading Argos model %s->%s (first use)...", from_code, to_code)
    package_mod.install_from_path(package.download())
