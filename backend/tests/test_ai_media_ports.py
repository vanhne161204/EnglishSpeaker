"""Translator and Transcriber ports (docs §18.2, §18.10).

The point of §18.2 is that these are NOT the LLM port: Google Translate has no
system prompt, and no Claude or GPT model accepts audio bytes. These tests assert
the two ports behave like the LLM one where it matters (fallback, degradation,
never taking a room down) without pretending they are the same thing.
"""

from __future__ import annotations

import pytest

from app.ai.errors import AllProvidersFailed, ProviderBadRequest, ProviderTimeout
from app.ai.providers.stub import FakeProvider
from app.ai.providers.transcribers import StubTranscriber
from app.ai.providers.translators import LLMTranslator, StubTranslator
from app.ai.stt_port import TranscriberChain, Transcript
from app.ai.translate_port import TranslateJob, Translation, TranslatorChain

JOB = TranslateJob(text="hello", target_lang="vi", source_lang="en")


class FakeTranslator:
    def __init__(self, name: str, text: str = "xin chao", raises: Exception | None = None):
        self.name = name
        self.calls = 0
        self._text = text
        self._raises = raises

    async def translate(self, job: TranslateJob) -> Translation:
        self.calls += 1
        if self._raises:
            raise self._raises
        return Translation(text=self._text, target_lang=job.target_lang, provider=self.name)


class FakeTranscriber:
    def __init__(self, name: str, text: str = "hello there", raises: Exception | None = None):
        self.name = name
        self.calls = 0
        self._text = text
        self._raises = raises

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        self.calls += 1
        if self._raises:
            raise self._raises
        return Transcript(text=self._text, language=language, provider=self.name)


# --- translator chain -----------------------------------------------------


async def test_translator_chain_uses_the_first_engine_that_works() -> None:
    primary = FakeTranslator("google")
    backup = FakeTranslator("argos", text="never used")

    result = await TranslatorChain([primary, backup]).translate(JOB)

    assert result.text == "xin chao"
    assert result.degraded is False
    assert backup.calls == 0


async def test_translator_chain_falls_through_and_marks_degraded() -> None:
    down = FakeTranslator("google", raises=ProviderTimeout("google"))
    backup = FakeTranslator("argos", text="xin chao (offline)")

    result = await TranslatorChain([down, backup]).translate(JOB)

    assert result.text == "xin chao (offline)"
    assert result.degraded is True


async def test_translator_chain_does_not_retry_a_bad_request() -> None:
    bad = FakeTranslator("google", raises=ProviderBadRequest("google", "bad lang code"))
    backup = FakeTranslator("argos")

    with pytest.raises(ProviderBadRequest):
        await TranslatorChain([bad, backup]).translate(JOB)
    assert backup.calls == 0


async def test_the_stub_ends_the_chain_so_translation_never_fails() -> None:
    chain = TranslatorChain(
        [FakeTranslator("google", raises=ProviderTimeout("g")), StubTranslator()]
    )
    result = await chain.translate(JOB)

    assert result.provider == "stub"
    assert "demo" in result.text
    assert result.degraded is True


async def test_translator_chain_raises_only_when_nothing_answers() -> None:
    chain = TranslatorChain(
        [
            FakeTranslator("a", raises=ProviderTimeout("a")),
            FakeTranslator("b", raises=ProviderTimeout("b")),
        ]
    )
    with pytest.raises(AllProvidersFailed):
        await chain.translate(JOB)


# --- LLMTranslator: the adapter doing its actual job ----------------------


async def test_llm_translator_adapts_a_language_model_to_the_translator_port() -> None:
    llm = FakeProvider(text="Xin chào")
    result = await LLMTranslator(llm).translate(JOB)

    assert result.text == "Xin chào"
    assert result.target_lang == "vi"
    # The prompt must name the target language, not just hope.
    assert "Vietnamese" in llm.calls[0].system


async def test_llm_translator_skips_the_call_when_languages_match() -> None:
    """Paying a model to translate English into English is pure waste."""
    llm = FakeProvider()
    same = TranslateJob(text="hello", target_lang="en", source_lang="en")

    result = await LLMTranslator(llm).translate(same)

    assert result.text == "hello"
    assert llm.calls == []


# --- transcriber chain ----------------------------------------------------


async def test_transcriber_chain_uses_the_first_engine_that_works() -> None:
    primary = FakeTranscriber("whisper")
    backup = FakeTranscriber("deepgram")

    result = await TranscriberChain([primary, backup]).transcribe(b"audio")

    assert result.text == "hello there"
    assert result.degraded is False
    assert backup.calls == 0


async def test_transcriber_chain_falls_through_when_whisper_is_missing() -> None:
    """faster-whisper is not installed everywhere; a cloud engine can cover it."""
    missing = FakeTranscriber("whisper", raises=ProviderTimeout("whisper"))
    cloud = FakeTranscriber("deepgram", text="hello from the cloud")

    result = await TranscriberChain([missing, cloud]).transcribe(b"audio")

    assert result.text == "hello from the cloud"
    assert result.degraded is True


async def test_transcriber_stub_ends_the_chain() -> None:
    chain = TranscriberChain(
        [FakeTranscriber("whisper", raises=ProviderTimeout("w")), StubTranscriber()]
    )
    result = await chain.transcribe(b"audio")

    assert result.provider == "stub"
    assert result.degraded is True


def test_empty_chains_are_rejected_at_construction() -> None:
    with pytest.raises(ValueError):
        TranslatorChain([])
    with pytest.raises(ValueError):
        TranscriberChain([])


# --- the ports stay separate on purpose (docs §18.2) ----------------------


def test_the_transcript_carries_fields_the_llm_port_has_no_place_for() -> None:
    """duration_s bills per-minute engines and feeds the fluency metrics;
    confidence becomes the pronunciation hint list (§10.3.8, §10.3.11)."""
    transcript = Transcript(
        text="hi", language="en", provider="deepgram", duration_s=4.2, confidence=0.91
    )
    assert transcript.duration_s == 4.2
    assert transcript.confidence == 0.91
