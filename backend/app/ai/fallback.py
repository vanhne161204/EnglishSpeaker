"""Shared fallback semantics for all three ports (docs §18.6).

``LLMProvider``, ``Translator`` and ``Transcriber`` have different method names,
but "try each engine in order, and know which failures are worth retrying" is the
same rule for all of them. It lives here once rather than being copy-pasted three
times and drifting.

The rule that matters: **retry transient failures, never retry your own bad
request.** A 400 falling through a three-engine chain turns one fast error into
three slow ones and buries the real cause.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from app.ai.errors import AllProvidersFailed, ProviderBadRequest, ProviderError

logger = logging.getLogger(__name__)


class _Named(Protocol):
    name: str


async def run_chain[P: _Named, R](
    providers: Sequence[P],
    call: Callable[[P], Awaitable[R]],
    mark_degraded: Callable[[R], R],
    kind: str = "AI",
) -> R:
    """Call each provider in turn; return the first success.

    ``mark_degraded`` is applied to any result that did not come from the first
    provider, so callers can tell "this is the model I asked for" from "this is
    what answered after the first one failed".
    """
    if not providers:
        raise ValueError("a fallback chain needs at least one provider")

    last_error: ProviderError | None = None

    for index, provider in enumerate(providers):
        try:
            result = await call(provider)
        except ProviderBadRequest:
            # Malformed request: every provider rejects it identically.
            raise
        except ProviderError as exc:
            if not exc.retryable:
                raise
            last_error = exc
            nxt = providers[index + 1].name if index + 1 < len(providers) else "nothing left"
            logger.warning(
                "%s provider %s failed (%s); falling back to %s",
                kind,
                provider.name,
                type(exc).__name__,
                nxt,
            )
            continue

        return result if index == 0 else mark_degraded(result)

    raise AllProvidersFailed(
        " -> ".join(p.name for p in providers), str(last_error) if last_error else ""
    )
