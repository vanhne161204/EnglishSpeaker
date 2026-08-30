"""Anthropic (Claude) adapter for the LLM port (docs §18.4).

Replaces the per-request ``AsyncAnthropic(...)`` construction currently inlined in
``services/assistant.py`` and ``services/translation.py``. Three things it fixes
beyond swappability: one shared client instead of a new connection pool per call,
a timeout on every request (the SDK default is 10 minutes), and handling of
``stop_reason == "refusal"``, which returns HTTP 200 and would otherwise surface
as a silently empty suggestion.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.ai.errors import (
    ProviderBadRequest,
    ProviderError,
    ProviderRateLimited,
    ProviderRefused,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.ai.ports import Capabilities, LLMRequest, LLMResponse, Usage
from app.ai.pricing import ModelPrice

logger = logging.getLogger(__name__)

#: Rough chars-per-token, only used to decide whether a prompt can reach the
#: model's cache minimum. Precision is not needed for a yes/no.
_CHARS_PER_TOKEN = 4


class AnthropicProvider:
    """Adapts the Anthropic Messages API to the ``LLMProvider`` port."""

    def __init__(
        self,
        model: str,
        price: ModelPrice,
        capabilities: Capabilities,
        client: Any,  # anthropic.AsyncAnthropic — untyped so the SDK stays optional
    ) -> None:
        self.name = f"anthropic:{model}"
        self.capabilities = capabilities
        self._model = model
        self._price = price
        self._client = client

    async def generate(self, request: LLMRequest) -> LLMResponse:
        import anthropic  # imported lazily so the SDK stays an optional dependency

        kwargs = self._build_kwargs(request)
        started = time.perf_counter()
        try:
            if request.schema is not None and self.capabilities.structured_output:
                message = await self._client.messages.parse(
                    output_format=request.schema, **kwargs
                )
                parsed = message.parsed_output
            else:
                message = await self._client.messages.create(**kwargs)
                parsed = None
        except anthropic.APITimeoutError as exc:
            raise ProviderTimeout(self.name) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimited(self.name) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailable(self.name, str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailable(self.name, str(exc)) from exc
            raise ProviderBadRequest(self.name, str(exc)) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        # A safety refusal is HTTP 200 with stop_reason="refusal" — it does not
        # raise. Check before reading content, or the learner gets an empty box.
        if getattr(message, "stop_reason", None) == "refusal":
            details = getattr(message, "stop_details", None)
            raise ProviderRefused(self.name, str(getattr(details, "category", "") or ""))

        text = "".join(b.text for b in message.content if b.type == "text").strip()
        usage = _usage_of(message)

        return LLMResponse(
            text=text,
            parsed=parsed,
            usage=usage,
            cost_usd=self._price.cost_of(usage),
            model=self._model,
            provider="anthropic",
            latency_ms=latency_ms,
        )

    def _build_kwargs(self, request: LLMRequest) -> dict[str, Any]:
        system: Any = request.system
        if request.cache_system and self._can_cache(request.system):
            system = [
                {
                    "type": "text",
                    "text": request.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": min(request.max_tokens, self.capabilities.max_output_tokens),
            "system": system,
            "messages": [{"role": "user", "content": request.user}],
            # Per-request timeout; never mutate the shared client.
            "timeout": request.timeout_s,
        }
        # Claude Haiku 4.5 returns 400 if sent an effort parameter. Keeping that
        # in `capabilities` is what stops it leaking into every call site.
        if request.effort in self.capabilities.effort_levels:
            kwargs["output_config"] = {"effort": request.effort.value}
        return kwargs

    def _can_cache(self, system: str) -> bool:
        """Whether marking the cache would do anything at all.

        Below the model's minimum the marker is silently ignored — no error, and
        `cache_read_input_tokens` just stays 0. Haiku 4.5 needs 4096 tokens,
        which the in-room coach prompt does not reach (docs/10_AI_Design §10.2).
        """
        return len(system) / _CHARS_PER_TOKEN >= self.capabilities.min_cacheable_tokens


def _usage_of(message: Any) -> Usage:
    usage = getattr(message, "usage", None)
    if usage is None:
        return Usage(input_tokens=0, output_tokens=0)
    return Usage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cached_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
    )


def build_client(api_key: str) -> Any:
    """Create the one shared ``AsyncAnthropic`` for this process.

    ``max_retries=0`` is deliberate. The SDK retries timeouts and 5xx itself, so
    a "3 second" request can take 9 seconds of wall clock — measured: a 3808 ms
    call sailed past a 3.0 s deadline because attempt 1 timed out and attempt 2
    succeeded. In a live room that is a hung UI.

    Retrying is ``FallbackChain``'s job (app/ai/chain.py), which moves to the
    NEXT provider instead of hammering the one that just failed. One retry
    mechanism, not two nested ones with a multiplying deadline.
    """
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ProviderError(
            "anthropic", "the `anthropic` package is not installed (`pip install anthropic`)"
        ) from exc
    return AsyncAnthropic(api_key=api_key, max_retries=0)
