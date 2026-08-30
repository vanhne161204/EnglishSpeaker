"""The LLM port — the only AI interface the rest of the app depends on.

See docs/18_AI_Provider_Architecture.md §18.3. Services import ``LLMProvider``
and never a vendor SDK, so swapping Claude for GPT (or adding a fallback) is a
configuration change rather than a code change.

Three deliberate omissions, each explained where it matters below: no sampling
parameters, no message history, no streaming. Adding a parameter that only one
vendor honours makes the port lie to its callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class Effort(StrEnum):
    """How hard the model should think. Each adapter maps this to its own knob.

    Claude maps it to ``output_config.effort``; OpenAI's reasoning models map it
    to ``reasoning_effort``; a model with neither ignores it (see
    ``Capabilities.effort_levels``).
    """

    low = "low"
    medium = "medium"
    high = "high"


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """One single-shot generation.

    No ``temperature`` / ``top_p`` / ``top_k``: Claude Opus 5 and Sonnet 5 removed
    sampling parameters and return 400 if one is sent, and OpenAI's reasoning
    models pin temperature to 1. A field the adapter would have to silently drop
    is worse than no field — the caller would believe they had set something.

    No message history: every AI task in this app is single-shot (rescue,
    translate, sentence check, IELTS report). Add it when something needs it.
    """

    system: str
    user: str
    max_tokens: int
    #: Hard deadline in seconds. No default on purpose — a forgotten timeout is
    #: how a live room hangs (the Anthropic SDK's own default is 10 minutes).
    timeout_s: float
    effort: Effort = Effort.medium
    #: Ask for a validated object instead of text. The adapter uses the vendor's
    #: native structured-output support; every adapter here has it.
    schema: type[BaseModel] | None = None
    #: Hint that ``system`` is large and stable enough to be worth caching. The
    #: adapter still checks it against its model's minimum before marking it.
    cache_system: bool = False


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    #: Input tokens served from the vendor's prompt cache (billed at ~0.1x).
    cached_input_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    parsed: BaseModel | None
    usage: Usage
    #: Computed by the adapter from its own price table. Decimal, never float —
    #: this ends up in a billing report (docs §18.8).
    cost_usd: Decimal
    model: str
    provider: str
    latency_ms: int
    #: True when a fallback produced this rather than the first choice. Services
    #: can soften the UI; ops should alert when this rate climbs.
    degraded: bool = False


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What one model can actually do.

    This exists so vendor quirks live in exactly one place. Two real examples
    that would otherwise leak into every call site: Claude Haiku 4.5 returns 400
    if sent an effort parameter, and a system prompt shorter than the model's
    minimum silently fails to cache (no error, no hit).
    """

    structured_output: bool
    #: EMPTY set means "this model has no effort knob — do not send one".
    effort_levels: frozenset[Effort]
    max_output_tokens: int
    #: Prompts shorter than this will not cache. Claude Opus 5 = 512,
    #: Claude Haiku 4.5 = 4096, OpenAI = 1024.
    min_cacheable_tokens: int
    accepts_audio: bool = False


@runtime_checkable
class LLMProvider(Protocol):
    """One model behind one call. Services depend on THIS, never on an SDK."""

    #: Stable key, e.g. "openai:gpt-5-nano". Used in config and in usage records.
    name: str
    capabilities: Capabilities

    async def generate(self, request: LLMRequest) -> LLMResponse: ...
