"""Model catalogue and provider construction (docs §18.5).

One place that knows every model the app can talk to, what each one can do, and
which vendor client it needs. Everything else refers to a model by its key —
``"openai:gpt-5-nano"``, ``"anthropic:claude-haiku-4-5"``, ``"stub"``.

Clients are built once per process and shared. A provider whose API key is
missing is skipped with a warning rather than raising, so setting only
``OPENAI_API_KEY`` is enough to run the whole app on OpenAI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cache, lru_cache
from typing import Any, Literal

from app.ai.chain import FallbackChain
from app.ai.errors import ProviderError
from app.ai.ports import Capabilities, Effort, LLMProvider
from app.ai.pricing import PRICES, ModelPrice
from app.ai.providers.stub import StubProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

Vendor = Literal["anthropic", "openai"]

_ALL_EFFORTS = frozenset({Effort.low, Effort.medium, Effort.high})
_NO_EFFORT: frozenset[Effort] = frozenset()


@dataclass(frozen=True, slots=True)
class ModelSpec:
    vendor: Vendor
    capabilities: Capabilities
    #: OpenAI only: newer models reject `max_tokens` and want
    #: `max_completion_tokens`. Per-model, because it is a per-model fact.
    max_tokens_field: str = "max_completion_tokens"
    #: OpenAI only: reasoning models bill invisible thinking against the SAME
    #: cap as the answer, so the adapter must add headroom or the reply comes
    #: back empty. Measured on gpt-5-nano: a 100-token cap returned 0 characters.
    reasoning_model: bool = False


#: Every model the app knows how to call, keyed by "<vendor>:<model>".
#:
#: `min_cacheable_tokens` is the prompt length below which caching silently does
#: nothing. It differs sharply between models and is the kind of vendor trivia
#: that belongs here rather than in a service.
CATALOGUE: dict[str, ModelSpec] = {
    # --- Anthropic ---
    "anthropic:claude-opus-5": ModelSpec(
        vendor="anthropic",
        capabilities=Capabilities(
            structured_output=True,
            effort_levels=_ALL_EFFORTS,
            max_output_tokens=64_000,
            min_cacheable_tokens=512,
        ),
    ),
    "anthropic:claude-sonnet-5": ModelSpec(
        vendor="anthropic",
        capabilities=Capabilities(
            structured_output=True,
            effort_levels=_ALL_EFFORTS,
            max_output_tokens=64_000,
            min_cacheable_tokens=1024,
        ),
    ),
    "anthropic:claude-haiku-4-5": ModelSpec(
        vendor="anthropic",
        capabilities=Capabilities(
            structured_output=True,
            # Haiku 4.5 returns 400 if sent an effort parameter.
            effort_levels=_NO_EFFORT,
            max_output_tokens=8192,
            # 4096 — the in-room coach prompt (~900 tokens) cannot reach this,
            # so `cache_system` is correctly a no-op there.
            min_cacheable_tokens=4096,
        ),
    ),
    # --- OpenAI ---
    # The cheapest model on either vendor. Default for local dev and CI.
    "openai:gpt-5-nano": ModelSpec(
        vendor="openai",
        reasoning_model=True,
        capabilities=Capabilities(
            structured_output=True,
            effort_levels=_ALL_EFFORTS,  # maps to `reasoning_effort`
            max_output_tokens=32_768,
            min_cacheable_tokens=1024,
        ),
    ),
    "openai:gpt-5-mini": ModelSpec(
        vendor="openai",
        reasoning_model=True,
        capabilities=Capabilities(
            structured_output=True,
            effort_levels=_ALL_EFFORTS,
            max_output_tokens=32_768,
            min_cacheable_tokens=1024,
        ),
    ),
    "openai:gpt-4.1-nano": ModelSpec(
        vendor="openai",
        capabilities=Capabilities(
            structured_output=True,
            effort_levels=_NO_EFFORT,  # not a reasoning model
            max_output_tokens=32_768,
            min_cacheable_tokens=1024,
        ),
    ),
    "openai:gpt-4o-mini": ModelSpec(
        vendor="openai",
        capabilities=Capabilities(
            structured_output=True,
            effort_levels=_NO_EFFORT,
            max_output_tokens=16_384,
            min_cacheable_tokens=1024,
        ),
    ),
}

STUB_KEY = "stub"


# --- shared clients -------------------------------------------------------
#
# Built once per process, not per request. The services being replaced construct
# a client inside the request handler, which throws away a connection pool on
# every call (docs §18.1, problem 1).


@lru_cache(maxsize=1)
def _anthropic_client() -> Any:
    from app.ai.providers.anthropic_provider import build_client

    if not settings.anthropic_api_key:
        raise ProviderError("anthropic", "ANTHROPIC_API_KEY is not set")
    return build_client(settings.anthropic_api_key)


@lru_cache(maxsize=1)
def _openai_client() -> Any:
    from app.ai.providers.openai_provider import build_client

    if not settings.openai_api_key:
        raise ProviderError("openai", "OPENAI_API_KEY is not set")
    return build_client(settings.openai_api_key)


def _price_for(model: str) -> ModelPrice:
    price = PRICES.get(model)
    if price is None:
        raise ProviderError(model, "no price entry — add it to app/ai/pricing.py")
    return price


@cache
def get_provider(key: str) -> LLMProvider:
    """Build (and cache) one provider by catalogue key.

    Raises ``ProviderError`` when the key is unknown, the vendor SDK is missing,
    or the API key is unset. Callers that want graceful degradation should use
    :func:`build_chain`, which skips unavailable providers instead.
    """
    if key == STUB_KEY:
        return StubProvider()

    spec = CATALOGUE.get(key)
    if spec is None:
        raise ProviderError(key, f"unknown model key — add it to {__name__}.CATALOGUE")

    model = key.split(":", 1)[1]
    price = _price_for(model)

    if spec.vendor == "anthropic":
        from app.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model, price, spec.capabilities, _anthropic_client())

    from app.ai.providers.openai_provider import OpenAIProvider

    return OpenAIProvider(
        model,
        price,
        spec.capabilities,
        _openai_client(),
        spec.max_tokens_field,
        spec.reasoning_model,
    )


def build_chain(keys: list[str]) -> LLMProvider:
    """Build a fallback chain from explicit model keys, skipping the unavailable.

    A model whose API key is unset or whose SDK is missing is dropped with a
    warning rather than raising — that is what lets you set only
    ``OPENAI_API_KEY`` and have the whole app run on OpenAI. The chain always
    ends in the stub, so the AI never takes a room down.

    Features do NOT call this directly: they use ``app.ai.factory.build_llm``,
    which reads the per-task chain from the routing table and adds metering and
    the budget guard. This is the low-level building block behind it.
    """
    if not settings.ai_enabled:
        logger.info("AI_ENABLED=false — every AI task will use the stub.")
        return StubProvider()

    providers: list[LLMProvider] = []
    for key in keys:
        if key == STUB_KEY:
            continue  # appended unconditionally below
        try:
            providers.append(get_provider(key))
        except ProviderError as exc:
            logger.warning("AI provider %s unavailable, skipping: %s", key, exc)

    if not providers:
        logger.warning(
            "No AI provider is configured (checked: %s). Running in demo mode — "
            "set OPENAI_API_KEY or ANTHROPIC_API_KEY to enable real AI.",
            ", ".join(keys),
        )

    providers.append(StubProvider())
    return FallbackChain(providers)


def reset_cache() -> None:
    """Drop cached clients and providers. For tests, and for a settings reload."""
    get_provider.cache_clear()
    _anthropic_client.cache_clear()
    _openai_client.cache_clear()
