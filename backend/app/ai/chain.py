"""Fallback across LLM providers (docs §18.6).

Itself an ``LLMProvider``, so it composes: a service holding a chain cannot tell
it apart from a single model. The retry rules live in ``app.ai.fallback``, shared
with the translator and transcriber chains.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from app.ai.fallback import run_chain
from app.ai.ports import LLMProvider, LLMRequest, LLMResponse


class FallbackChain:
    """Try each provider in order; the first success wins."""

    def __init__(self, providers: Sequence[LLMProvider]) -> None:
        if not providers:
            raise ValueError("a fallback chain needs at least one provider")
        self._providers = tuple(providers)
        self.name = " -> ".join(p.name for p in self._providers)
        # Advertise the primary's capabilities: callers shape requests for the
        # model they expect to get, and every adapter drops what it cannot use.
        self.capabilities = self._providers[0].capabilities

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return await run_chain(
            self._providers,
            lambda provider: provider.generate(request),
            lambda response: replace(response, degraded=True),
            kind="LLM",
        )
