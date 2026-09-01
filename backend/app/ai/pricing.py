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
