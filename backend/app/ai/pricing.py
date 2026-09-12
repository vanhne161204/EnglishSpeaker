"""Per-model prices, and the cost of one call (docs §18.4, §18.8).

Every adapter knows its own prices, so ``LLMResponse.cost_usd`` is filled in for
free and the ``ai_usage`` table can answer the only question that decides your
pricing: *what does one user cost me per month?*

``Decimal`` throughout, never ``float`` — this is money that ends up in a billing
report, and a single call costs about $0.0016, so binary rounding error is not
academic here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.ai.ports import Usage

#: Bump this whenever you re-check the vendors' pricing pages. A stale table
#: under-reports costs and quietly wrecks the margin model in docs §18.9.
PRICES_VERIFIED_ON = date(2026, 8, 29)

_PER_MILLION = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """USD per 1M tokens."""

    input_per_mtok: Decimal
    output_per_mtok: Decimal
    cached_input_per_mtok: Decimal

    def cost_of(self, usage: Usage) -> Decimal:
        """What this call cost, counting cached input at its discounted rate."""
        fresh_input = max(usage.input_tokens - usage.cached_input_tokens, 0)
        return (
            Decimal(fresh_input) * self.input_per_mtok
            + Decimal(usage.cached_input_tokens) * self.cached_input_per_mtok
            + Decimal(usage.output_tokens) * self.output_per_mtok
        ) / _PER_MILLION


def _d(value: str) -> Decimal:
    # Always construct Decimal from a string: Decimal(0.05) captures the binary
    # float's error, Decimal("0.05") does not.
    return Decimal(value)


#: Keyed by bare model id (no vendor prefix).
#:
#: Anthropic:  docs.claude.com/en/docs/about-claude/pricing
#: OpenAI:     developers.openai.com/api/docs/pricing
#:
#: Cached-input rates are the vendors' documented discounts (~0.1x). Treat them
#: as approximate for OpenAI — verify before quoting a margin off them.
PRICES: dict[str, ModelPrice] = {
    # --- Anthropic ---
    "claude-opus-5": ModelPrice(_d("5.00"), _d("25.00"), _d("0.50")),
    "claude-sonnet-5": ModelPrice(_d("2.00"), _d("10.00"), _d("0.20")),
    "claude-haiku-4-5": ModelPrice(_d("1.00"), _d("5.00"), _d("0.10")),
    # --- OpenAI ---
    # gpt-5-nano is the cheapest text model on either vendor by a wide margin:
    # ~20x cheaper input than Haiku 4.5. That makes it the right default for
    # local development and integration tests (docs §18.9).
    "gpt-5-nano": ModelPrice(_d("0.05"), _d("0.40"), _d("0.005")),
    "gpt-4.1-nano": ModelPrice(_d("0.10"), _d("0.40"), _d("0.01")),
    "gpt-4o-mini": ModelPrice(_d("0.15"), _d("0.60"), _d("0.015")),
    "gpt-5-mini": ModelPrice(_d("0.25"), _d("2.00"), _d("0.025")),
}

#: Charged for a stub response, so cost arithmetic never special-cases it.
FREE = ModelPrice(Decimal(0), Decimal(0), Decimal(0))


# --- Non-token pricing -----------------------------------------------------
#
# Two engines in this system do not bill per token, and pretending they do would
# put a wrong number in the ledger. Translation bills per CHARACTER and
# speech-to-text bills per audio MINUTE, so each gets its own rate.
#
# These exist so the spend dashboard cannot quietly become wrong the day one of
# them is switched on. Both are $0 in the default configuration: translation
# falls back to Argos (local) or Google's free endpoint when no API key is set,
# and speech-to-text runs in the learner's browser.

#: USD per 1M characters, Google Cloud Translation v2 (only billed with an API key).
GOOGLE_TRANSLATE_PER_MCHAR = _d("20.00")

#: USD per audio minute, Deepgram Nova pay-as-you-go (pre-recorded).
DEEPGRAM_PER_MINUTE = _d("0.0043")


def google_translate_cost(characters: int) -> Decimal:
    """What one Google Translate call cost. Zero without a key — the free
    endpoint is not billed, and recording a phantom charge is worse than
    recording nothing."""
    return (Decimal(max(characters, 0)) * GOOGLE_TRANSLATE_PER_MCHAR) / _PER_MILLION


def deepgram_cost(duration_s: float | None) -> Decimal:
    """What one Deepgram call cost, from the audio length it reports back."""
    if not duration_s or duration_s <= 0:
        return Decimal(0)
    return (Decimal(str(duration_s)) / Decimal(60)) * DEEPGRAM_PER_MINUTE


# --- Gemini Live (voice-to-voice, PRD §8.12) -------------------------------
#
# Paid tier, from ai.google.dev/gemini-api/docs/pricing. Live bills audio as
# tokens: 25 tokens per second of audio, in both directions.
#
# The server never sees the audio — the browser streams it straight to Google —
# so the cost is an ESTIMATE from session length. The learner's mic is streamed
# for the whole session (silence included), and the coach is assumed to talk
# for half of it. Reconcile against the Google invoice before quoting a margin.

GEMINI_PRICES_VERIFIED_ON = date(2026, 9, 10)

GEMINI_LIVE_AUDIO_TOKENS_PER_SECOND = 25
GEMINI_LIVE_ASSUMED_COACH_TALK_SHARE = _d("0.5")

_DEFAULT_LIVE_MODEL = "gemini-3.1-flash-live-preview"


@dataclass(frozen=True, slots=True)
class AudioPrice:
    """USD per 1M audio tokens."""

    input_per_mtok: Decimal
    output_per_mtok: Decimal


GEMINI_LIVE_PRICES: dict[str, AudioPrice] = {
    _DEFAULT_LIVE_MODEL: AudioPrice(_d("3.00"), _d("12.00")),
    "gemini-2.5-flash-native-audio-preview-12-2025": AudioPrice(_d("3.00"), _d("12.00")),
}


def gemini_live_tokens(seconds: int) -> tuple[int, int]:
    """(audio tokens in, audio tokens out), estimated for a session this long."""
    tokens_in = max(seconds, 0) * GEMINI_LIVE_AUDIO_TOKENS_PER_SECOND
    tokens_out = int(Decimal(tokens_in) * GEMINI_LIVE_ASSUMED_COACH_TALK_SHARE)
    return tokens_in, tokens_out


def gemini_live_cost(model: str, seconds: int) -> Decimal:
    """Estimated cost of one Live session.

    An unknown model is priced like the default one, not as free: a model
    missing from the table must not make the voice coach look cheap.
    """
    price = GEMINI_LIVE_PRICES.get(model, GEMINI_LIVE_PRICES[_DEFAULT_LIVE_MODEL])
    tokens_in, tokens_out = gemini_live_tokens(seconds)
    return (
        Decimal(tokens_in) * price.input_per_mtok + Decimal(tokens_out) * price.output_per_mtok
    ) / _PER_MILLION


# --- Gemini text-to-speech (Shadowing, PRD §8.14) ---------------------------
#
# Paid tier, ai.google.dev/gemini-api/docs/pricing (checked 2026-09-10): text in
# and audio out, per 1M tokens, audio at 25 tokens per second. A clip is made once
# per sentence and stored, so this is a one-off cost, not a per-play one.


@dataclass(frozen=True, slots=True)
class TtsPrice:
    """USD per 1M tokens."""

    text_in_per_mtok: Decimal
    audio_out_per_mtok: Decimal


_DEFAULT_TTS_MODEL = "gemini-3.1-flash-tts-preview"

GEMINI_TTS_PRICES: dict[str, TtsPrice] = {
    _DEFAULT_TTS_MODEL: TtsPrice(_d("1.00"), _d("20.00")),
    "gemini-2.5-flash-preview-tts": TtsPrice(_d("0.50"), _d("10.00")),
}


def gemini_tts_cost(
    model: str, input_tokens: int, output_tokens: int, duration_ms: int
) -> Decimal:
    """Cost of one clip, from the tokens Gemini reported.

    If it reported no output tokens, the audio tokens are estimated from the clip
    length, so a missing usage block cannot make a clip look free. An unknown
    model is priced like the default one, for the same reason.
    """
    price = GEMINI_TTS_PRICES.get(model, GEMINI_TTS_PRICES[_DEFAULT_TTS_MODEL])
    audio_tokens = output_tokens or (
        max(duration_ms, 0) * GEMINI_LIVE_AUDIO_TOKENS_PER_SECOND + 999
    ) // 1000
    return (
        Decimal(max(input_tokens, 0)) * price.text_in_per_mtok
        + Decimal(audio_tokens) * price.audio_out_per_mtok
    ) / _PER_MILLION


# --- Azure Pronunciation Assessment (Shadowing Phase 2, PRD §8.14) ------------
#
# Retail prices from prices.azure.com, checked 2026-09-12 and the same in
# southeastasia and centralindia: "S1 Speech To Text" $1.00/hour and "S1 Speech to
# Text Enhanced Feature Audio" $0.30/hour. Pronunciation assessment bills as
# speech to text; the prosody score is the add-on (learn.microsoft.com, "How to
# use pronunciation assessment in the Microsoft Foundry portal", Pricing).
#
# A free F0 resource bills nothing, but the ledger records the pay-as-you-go
# price anyway, so the admin panel shows what the feature WOULD cost.

AZURE_STT_PER_HOUR = _d("1.00")
AZURE_PROSODY_ADDON_PER_HOUR = _d("0.30")


def azure_pronunciation_cost(seconds: float, prosody: bool) -> Decimal:
    """What one pronunciation check costs, from the length of the audio."""
    per_hour = AZURE_STT_PER_HOUR + (AZURE_PROSODY_ADDON_PER_HOUR if prosody else Decimal(0))
    return Decimal(str(max(seconds, 0.0))) * per_hour / Decimal(3600)
