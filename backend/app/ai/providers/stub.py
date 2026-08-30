"""Zero-config providers: a labelled stub, and a fake for tests.

``StubProvider`` is the last link in every fallback chain. It keeps the existing
promise that the app runs with no API key at all and that a live room never dies
because a vendor is down — the AI extras just go quiet and say so (docs §18.5).

``FakeProvider`` is what makes services testable without a key or a network,
which they are not today.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.ai.ports import Capabilities, Effort, LLMProvider, LLMRequest, LLMResponse, Usage

STUB_CAPABILITIES = Capabilities(
    structured_output=False,
    effort_levels=frozenset(),
    max_output_tokens=4096,
    min_cacheable_tokens=10**9,  # effectively never
)

_STUB_TEXT = "[demo mode — set an AI API key to get real suggestions]"


class StubProvider:
    """Always succeeds, costs nothing, and says plainly that it is a stub."""

    name = "stub"
    capabilities = STUB_CAPABILITIES

    def __init__(self, text: str = _STUB_TEXT) -> None:
        self._text = text

    async def generate(self, request: LLMRequest) -> LLMResponse:
        parsed: BaseModel | None = None
        if request.schema is not None:
            # A stub cannot invent a valid instance of an arbitrary schema, so
            # callers that need structured output must handle `parsed is None`.
            parsed = None
        return LLMResponse(
            text=self._text,
            parsed=parsed,
            usage=Usage(input_tokens=0, output_tokens=0),
            cost_usd=Decimal(0),
            model="stub",
            provider="stub",
            latency_ms=0,
            degraded=True,
        )


class FakeProvider:
    """Test double: returns canned output, or raises what you tell it to.

    Lets a service test assert real behaviour — including the timeout and
    fallback paths — with no API key, no network, and no SDK installed.
    """

    capabilities = Capabilities(
        structured_output=True,
        effort_levels=frozenset({Effort.low, Effort.medium, Effort.high}),
        max_output_tokens=8192,
        min_cacheable_tokens=0,
    )

    def __init__(
        self,
        name: str = "fake",
        text: str = "ok",
        parsed: BaseModel | None = None,
        raises: Exception | None = None,
        cost_usd: Decimal = Decimal("0.001"),
    ) -> None:
        self.name = name
        self.calls: list[LLMRequest] = []
        self._text = text
        self._parsed = parsed
        self._raises = raises
        self._cost = cost_usd

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self._raises is not None:
            raise self._raises
        return LLMResponse(
            text=self._text,
            parsed=self._parsed,
            usage=Usage(input_tokens=100, output_tokens=50),
            cost_usd=self._cost,
            model=self.name,
            provider="fake",
            latency_ms=1,
        )


def _assert_is_provider(candidate: Any) -> LLMProvider:
    """Typing aid: fails at import time if a class drifts from the port."""
    return candidate
