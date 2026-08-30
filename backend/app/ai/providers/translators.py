"""Translation engines behind the ``Translator`` port (docs §18.10).

Four adapters, all interchangeable:

* ``GoogleTranslator`` — best Vietnamese quality; official API with a key, or the
  free public endpoint without one.
* ``ArgosTranslator``  — offline neural MT. No network at translate time, so it
  is the private option; heavy to install (see requirements.txt).
* ``LLMTranslator``    — wraps an ``LLMProvider``. The Adapter pattern doing its
  actual job: making a language model fit a port it was not designed for.
* ``StubTranslator``   — labelled demo echo, so the app runs with zero setup.

Every engine raises the shared ``ProviderError`` family, so ``TranslatorChain``
can fall back without knowing which engine failed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.ai.errors import ProviderTimeout, ProviderUnavailable
from app.ai.ports import LLMProvider, LLMRequest
from app.ai.translate_port import TranslateJob, Translation

logger = logging.getLogger(__name__)

#: Friendly names for LLM prompts and the stub label.
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

#: The app's primary pair, used to guess the source when a caller omits it.
#: Argos needs an explicit source — it has no language detection of its own.
_DEFAULT_PAIR = ("en", "vi")

_HTTP_TIMEOUT_S = 10.0


def guess_source(target_lang: str) -> str:
    first, second = _DEFAULT_PAIR
    return first if target_lang.lower() != first else second


def _passthrough(job: TranslateJob, provider: str) -> Translation | None:
    """Same language in and out — no engine call needed."""
    source = (job.source_lang or "").lower()
    if source and source == job.target_lang.lower():
        return Translation(text=job.text, target_lang=job.target_lang, provider=provider)
    return None


class GoogleTranslator:
    name = "google"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def translate(self, job: TranslateJob) -> Translation:
        if (done := _passthrough(job, self.name)) is not None:
            return done

        import httpx

        # Google auto-detects, so an omitted source is fine here.
        source = (job.source_lang or "auto").lower()
        target = job.target_lang.lower()
        try:
            if self._api_key:
                text = await _google_official(job.text, source, target, self._api_key)
            else:
                text = await _google_free(job.text, source, target)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(self.name) from exc
        except Exception as exc:  # noqa: BLE001 — any API/parse failure: try the next engine
            raise ProviderUnavailable(self.name, str(exc)) from exc

        if not text:
            raise ProviderUnavailable(self.name, "empty translation")
        return Translation(text=text, target_lang=job.target_lang, provider=self.name)


class ArgosTranslator:
    name = "argos"

    def __init__(self, auto_download: bool = True) -> None:
        self._auto_download = auto_download

    async def translate(self, job: TranslateJob) -> Translation:
        source = (job.source_lang or guess_source(job.target_lang)).lower()
        target = job.target_lang.lower()
        if source == target:
            return Translation(text=job.text, target_lang=job.target_lang, provider=self.name)

        # Argos is blocking CPU work — keep it off the event loop.
        text = await asyncio.to_thread(
            _argos_translate, job.text, source, target, self._auto_download
        )
        if text is None:
            raise ProviderUnavailable(self.name, f"no model for {source}->{target}")
        return Translation(text=text, target_lang=job.target_lang, provider=self.name)


class LLMTranslator:
    """Adapts an ``LLMProvider`` to the ``Translator`` port.

    Inherits the LLM chain's fallback, cost metering and budget guard for free —
    translation spend lands in ``ai_usage`` alongside everything else with no
    extra code.
    """

    name = "llm"

    def __init__(self, llm: LLMProvider, max_tokens: int = 1024, timeout_s: float = 10.0) -> None:
        self._llm = llm
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s

    async def translate(self, job: TranslateJob) -> Translation:
        if (done := _passthrough(job, self.name)) is not None:
            return done

        target_name = LANGUAGE_NAMES.get(job.target_lang, job.target_lang)
        source_clause = ""
        if job.source_lang:
            source_name = LANGUAGE_NAMES.get(job.source_lang, job.source_lang)
            source_clause = f" The text is in {source_name}."

        response = await self._llm.generate(
            LLMRequest(
                system=(
                    "You are a translation engine for a language-learning app. "
                    f"Translate the user's message into {target_name}.{source_clause} "
                    "Reply with ONLY the translation — no quotes, no explanations, no notes."
                ),
                user=job.text,
                max_tokens=self._max_tokens,
                timeout_s=self._timeout_s,
            )
        )
        if not response.text:
            raise ProviderUnavailable(self.name, "empty translation")
        return Translation(
            text=response.text,
            target_lang=job.target_lang,
            provider=response.provider,
            degraded=response.degraded,
        )


class StubTranslator:
    """Never fails. Last link in the chain so the app runs with zero setup."""

    name = "stub"

    async def translate(self, job: TranslateJob) -> Translation:
        target_name = LANGUAGE_NAMES.get(job.target_lang, job.target_lang)
        return Translation(
            text=f"[demo → {target_name}] {job.text}",
            target_lang=job.target_lang,
            provider=self.name,
            degraded=True,
        )


# --- Google HTTP ----------------------------------------------------------


async def _google_free(text: str, source: str, target: str) -> str:
    """Translate via Google's free public endpoint (no key; unofficial)."""
    import httpx

    params = {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
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
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
        resp = await client.post(
            "https://translation.googleapis.com/language/translate/v2",
            params={"key": api_key},
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
    return str(data["data"]["translations"][0]["translatedText"])


# --- Argos ----------------------------------------------------------------

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


def _argos_translate(text: str, from_code: str, to_code: str, auto_download: bool) -> str | None:
    """Translate with Argos, or return ``None`` so the caller can fall back.

    Runs in a worker thread. Returns ``None`` (never raises) when the package or
    the required language model is unavailable.
    """
    try:
        import argostranslate.translate as translate_mod
    except ImportError:
        logger.warning(
            "argostranslate not installed. `pip install argostranslate` to enable "
            "offline translation."
        )
        return None

    _silence_argos_logging()

    try:
        # Check the translation *direction*, not just the languages: installing
        # en->vi creates both language objects but only the en->vi model, so a
        # vi->en request must still trigger its own download.
        translation = _installed_translation(translate_mod, from_code, to_code)
        if translation is None and auto_download:
            _install_pair(from_code, to_code)
            translation = _installed_translation(translate_mod, from_code, to_code)

        if translation is None:
            logger.warning("No Argos model installed for %s->%s", from_code, to_code)
            return None

        return str(translation.translate(text))
    except Exception as exc:  # noqa: BLE001 — any engine error: let the chain fall back
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
