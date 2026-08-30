"""Tests for the AI provider layer (docs/18_AI_Provider_Architecture.md).

All offline: no API key, no network, no vendor SDK required. That is the point
of the port — the current services cannot be tested at all without a live key.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.ai.chain import FallbackChain
from app.ai.errors import (
    AllProvidersFailed,
    ProviderBadRequest,
    ProviderRateLimited,
    ProviderRefused,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.ai.ports import Capabilities, Effort, LLMRequest, Usage
from app.ai.pricing import PRICES, ModelPrice
from app.ai.providers.openai_provider import OpenAIProvider, to_strict_schema
from app.ai.providers.stub import FakeProvider, StubProvider
from app.ai.registry import CATALOGUE, build_chain

# `asyncio_mode = "auto"` in pyproject.toml runs async tests without a marker.


def _request(**overrides) -> LLMRequest:
    base = {"system": "s", "user": "u", "max_tokens": 100, "timeout_s": 5.0}
    return LLMRequest(**{**base, **overrides})


# --- pricing --------------------------------------------------------------


def test_cost_counts_cached_input_at_the_discounted_rate() -> None:
    price = ModelPrice(Decimal("1.00"), Decimal("5.00"), Decimal("0.10"))
    # 1000 input of which 400 cached, 200 output.
    cost = price.cost_of(Usage(input_tokens=1000, output_tokens=200, cached_input_tokens=400))
    # 600 fresh @ $1 + 400 cached @ $0.10 + 200 out @ $5, all per 1M.
    expected = (Decimal(600) * 1 + Decimal(400) * Decimal("0.10") + Decimal(200) * 5) / 1_000_000
    assert cost == expected


def test_gpt_5_nano_is_the_cheapest_model_we_know() -> None:
    """Guards the list price the routing table's comments quote."""
    cheapest = min(PRICES.items(), key=lambda kv: kv[1].input_per_mtok)
    assert cheapest[0] == "gpt-5-nano"


def test_every_catalogue_model_has_a_price() -> None:
    """A model you can select but cannot cost would silently break ai_usage."""
    for key in CATALOGUE:
        assert key.split(":", 1)[1] in PRICES, f"{key} has no price entry"


# --- OpenAI strict schema -------------------------------------------------


class _Inner(BaseModel):
    wrong: str
    why: str


class _Outer(BaseModel):
    corrected: str | None
    errors: list[_Inner]
    score: int


def test_strict_schema_locks_every_object_down() -> None:
    """OpenAI strict mode rejects a schema without these two properties."""
    schema = to_strict_schema(_Outer)

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"corrected", "errors", "score"}

    # Nested models under $defs must be tightened too, or the API 400s.
    inner = schema["$defs"]["_Inner"]
    assert inner["additionalProperties"] is False
    assert set(inner["required"]) == {"wrong", "why"}


def test_strict_schema_keeps_optional_fields_nullable_not_absent() -> None:
    """`str | None` stays expressible: strict mode wants it required-but-null."""
    schema = to_strict_schema(_Outer)
    assert "corrected" in schema["required"]
    assert "anyOf" in schema["properties"]["corrected"]


# --- fallback chain -------------------------------------------------------


async def test_chain_returns_the_first_success_undegraded() -> None:
    primary = FakeProvider(name="primary", text="first")
    backup = FakeProvider(name="backup", text="second")

    response = await FallbackChain([primary, backup]).generate(_request())

    assert response.text == "first"
    assert response.degraded is False
    assert not backup.calls


async def test_chain_falls_through_transient_failure_and_marks_degraded() -> None:
    primary = FakeProvider(name="primary", raises=ProviderTimeout("primary"))
    backup = FakeProvider(name="backup", text="rescued")

    response = await FallbackChain([primary, backup]).generate(_request())

    assert response.text == "rescued"
    assert response.degraded is True


async def test_chain_never_retries_our_own_bad_request() -> None:
    """A 400 fails identically everywhere — falling through hides the bug."""
    primary = FakeProvider(name="primary", raises=ProviderBadRequest("primary", "bad schema"))
    backup = FakeProvider(name="backup", text="never reached")

    with pytest.raises(ProviderBadRequest):
        await FallbackChain([primary, backup]).generate(_request())

    assert not backup.calls


async def test_chain_raises_when_everything_fails() -> None:
    chain = FallbackChain(
        [
            FakeProvider(name="a", raises=ProviderTimeout("a")),
            FakeProvider(name="b", raises=ProviderRateLimited("b")),
        ]
    )
    with pytest.raises(AllProvidersFailed):
        await chain.generate(_request())


def test_chain_rejects_an_empty_provider_list() -> None:
    with pytest.raises(ValueError):
        FallbackChain([])


# --- stub / degradation ---------------------------------------------------


async def test_stub_always_succeeds_and_costs_nothing() -> None:
    response = await StubProvider().generate(_request())

    assert response.cost_usd == Decimal(0)
    assert response.degraded is True
    assert "demo mode" in response.text


async def test_build_chain_without_keys_still_answers(monkeypatch) -> None:
    """No API key must never take a room down — it degrades to the stub."""
    from app.core import config

    monkeypatch.setattr(config.settings, "anthropic_api_key", None)
    monkeypatch.setattr(config.settings, "openai_api_key", None)
    monkeypatch.setattr(config.settings, "ai_enabled", True)

    response = await build_chain(["openai:gpt-4o-mini"]).generate(_request())
    assert response.provider == "stub"


async def test_ai_enabled_false_is_a_hard_kill_switch(monkeypatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.settings, "ai_enabled", False)

    response = await build_chain(["openai:gpt-5-nano"]).generate(_request())
    assert response.provider == "stub"


# --- OpenAI adapter: request building (no network) ------------------------


class _FakeCompletions:
    """Captures the kwargs the adapter sends, and returns a canned completion."""

    def __init__(
        self,
        message_content: str | None = "hello",
        refusal: str | None = None,
        finish_reason: str = "stop",
        reasoning_tokens: int = 0,
    ) -> None:
        self.kwargs: dict = {}
        self._content = message_content
        self._refusal = refusal
        self._finish_reason = finish_reason
        self._reasoning = reasoning_tokens

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._content, refusal=self._refusal),
                    finish_reason=self._finish_reason,
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=120,
                completion_tokens=30,
                prompt_tokens_details=SimpleNamespace(cached_tokens=20),
                completion_tokens_details=SimpleNamespace(reasoning_tokens=self._reasoning),
            ),
        )


def _openai_provider(model: str, completions: _FakeCompletions) -> OpenAIProvider:
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    spec = CATALOGUE[f"openai:{model}"]
    return OpenAIProvider(
        model,
        PRICES[model],
        spec.capabilities,
        client,
        spec.max_tokens_field,
        spec.reasoning_model,
    )


async def test_reasoning_models_get_headroom_above_the_requested_answer_size() -> None:
    """Measured: gpt-5-nano with a 100-token cap spends it all thinking and
    returns an EMPTY string. The port's max_tokens means *answer* tokens, so the
    adapter must add room for invisible reasoning."""
    completions = _FakeCompletions()
    await _openai_provider("gpt-5-nano", completions).generate(
        _request(max_tokens=100, effort=Effort.low)
    )
    assert completions.kwargs["max_completion_tokens"] == 100 + 1024

    high = _FakeCompletions()
    await _openai_provider("gpt-5-nano", high).generate(
        _request(max_tokens=100, effort=Effort.high)
    )
    assert high.kwargs["max_completion_tokens"] == 100 + 4096


async def test_non_reasoning_models_get_no_headroom() -> None:
    completions = _FakeCompletions()
    await _openai_provider("gpt-4o-mini", completions).generate(_request(max_tokens=100))
    assert completions.kwargs["max_completion_tokens"] == 100


async def test_empty_answer_from_a_hit_cap_is_an_error_not_a_blank_reply() -> None:
    """Returning "" here would show the learner a blank box with a clean log."""
    completions = _FakeCompletions(
        message_content="", finish_reason="length", reasoning_tokens=100
    )
    with pytest.raises(ProviderUnavailable) as excinfo:
        await _openai_provider("gpt-5-nano", completions).generate(_request())
    assert "100 reasoning tokens" in str(excinfo.value)


async def test_truncated_structured_output_falls_through_rather_than_aborting() -> None:
    """Truncated JSON is unusable; a different model may fit the same budget."""
    completions = _FakeCompletions(message_content='{"wrong":"go"', finish_reason="length")
    with pytest.raises(ProviderUnavailable):
        await _openai_provider("gpt-5-nano", completions).generate(_request(schema=_Inner))


def test_openai_sdk_still_exposes_what_the_adapter_uses() -> None:
    """Catches SDK drift: these are the exact names openai_provider.py depends on."""
    openai = pytest.importorskip("openai")
    for name in (
        "APITimeoutError",
        "RateLimitError",
        "APIConnectionError",
        "APIStatusError",
        "AsyncOpenAI",
    ):
        assert hasattr(openai, name), f"openai.{name} is gone — adapter needs updating"

    params = inspect.signature(openai.AsyncOpenAI(api_key="x").chat.completions.create).parameters
    for param in ("model", "messages", "max_completion_tokens", "reasoning_effort",
                  "response_format", "timeout"):
        assert param in params, f"chat.completions.create lost `{param}`"


def test_anthropic_sdk_still_exposes_what_the_adapter_uses() -> None:
    """Guards the `anthropic>=1.0` pin in requirements.txt.

    `messages.parse()` and `output_config` do not exist in 0.x. A 0.x resolve
    installs cleanly and looks fine until the first Anthropic-routed request,
    then fails with AttributeError — in production, on the fallback path, which
    is exactly when you least want to discover it.
    """
    anthropic = pytest.importorskip("anthropic")
    for name in ("APITimeoutError", "RateLimitError", "APIConnectionError", "APIStatusError"):
        assert hasattr(anthropic, name), f"anthropic.{name} is gone"

    client = anthropic.AsyncAnthropic(api_key="sk-ant-x")
    assert hasattr(client.messages, "parse"), "messages.parse() missing — is this anthropic 0.x?"

    params = inspect.signature(client.messages.create).parameters
    for param in ("model", "max_tokens", "system", "messages", "timeout", "output_config"):
        assert param in params, f"messages.create lost `{param}`"


async def test_openai_sends_max_completion_tokens_not_max_tokens() -> None:
    """Newer OpenAI models reject `max_tokens` outright.

    Asserted on a non-reasoning model so the cap passes through unchanged;
    reasoning headroom has its own test below.
    """
    completions = _FakeCompletions()
    await _openai_provider("gpt-4o-mini", completions).generate(_request(max_tokens=250))

    assert completions.kwargs["max_completion_tokens"] == 250
    assert "max_tokens" not in completions.kwargs
    assert completions.kwargs["timeout"] == 5.0


async def test_openai_sends_reasoning_effort_only_to_reasoning_models() -> None:
    reasoning = _FakeCompletions()
    await _openai_provider("gpt-5-nano", reasoning).generate(_request(effort=Effort.low))
    assert reasoning.kwargs["reasoning_effort"] == "low"

    # gpt-4o-mini is not a reasoning model and 400s on the parameter.
    plain = _FakeCompletions()
    await _openai_provider("gpt-4o-mini", plain).generate(_request(effort=Effort.low))
    assert "reasoning_effort" not in plain.kwargs


async def test_openai_caps_max_tokens_at_the_model_limit() -> None:
    completions = _FakeCompletions()
    await _openai_provider("gpt-4o-mini", completions).generate(_request(max_tokens=10**9))
    assert completions.kwargs["max_completion_tokens"] == 16_384


async def test_openai_computes_cost_and_counts_cached_tokens() -> None:
    completions = _FakeCompletions()
    response = await _openai_provider("gpt-5-nano", completions).generate(_request())

    assert response.provider == "openai"
    assert response.usage.cached_input_tokens == 20
    assert response.cost_usd == PRICES["gpt-5-nano"].cost_of(response.usage)
    assert response.cost_usd > 0


async def test_openai_raises_on_a_refusal_instead_of_returning_empty() -> None:
    """A refusal is HTTP 200 with `message.refusal` — it must not look like success."""
    completions = _FakeCompletions(message_content=None, refusal="I can't help with that")
    with pytest.raises(ProviderRefused):
        await _openai_provider("gpt-5-nano", completions).generate(_request())


async def test_openai_attaches_a_strict_json_schema_when_asked() -> None:
    completions = _FakeCompletions(message_content='{"wrong":"go","why":"past tense"}')
    response = await _openai_provider("gpt-5-nano", completions).generate(
        _request(schema=_Inner)
    )

    fmt = completions.kwargs["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["additionalProperties"] is False
    assert isinstance(response.parsed, _Inner)
    assert response.parsed.wrong == "go"


async def test_openai_treats_unparseable_output_as_our_bug_not_a_retry() -> None:
    completions = _FakeCompletions(message_content="not json at all")
    with pytest.raises(ProviderBadRequest):
        await _openai_provider("gpt-5-nano", completions).generate(_request(schema=_Inner))


# --- capabilities ---------------------------------------------------------


def test_haiku_declares_no_effort_support() -> None:
    """Claude Haiku 4.5 returns 400 if sent an effort param — capability guards it."""
    assert CATALOGUE["anthropic:claude-haiku-4-5"].capabilities.effort_levels == frozenset()


def test_gpt_5_nano_supports_reasoning_effort() -> None:
    assert Effort.low in CATALOGUE["openai:gpt-5-nano"].capabilities.effort_levels


def test_cache_minimums_match_the_documented_values() -> None:
    """These differ sharply per model and silently no-op when unmet (docs §10.2)."""
    caps: dict[str, Capabilities] = {k: v.capabilities for k, v in CATALOGUE.items()}
    assert caps["anthropic:claude-opus-5"].min_cacheable_tokens == 512
    assert caps["anthropic:claude-haiku-4-5"].min_cacheable_tokens == 4096
