"""OpenAI (ChatGPT) adapter for the LLM port (docs §18.4).

Peer of ``AnthropicProvider``: same port, same five errors, same cost accounting.
Nothing outside this file knows the app can talk to OpenAI.

Model choice is NOT made here — see app/ai/routing.py. Two measured findings
shape those routes, and both are counter-intuitive:

* **gpt-5-nano has the lowest list price but is not the cheapest.** It is a
  reasoning model and bills 100-200 invisible thinking tokens as output to write
  one sentence, making it ~5x dearer per short call than gpt-4o-mini. It is also
  slower and far more variable (1.75s-5.7s vs 1.3s).
* **Its reasoning tokens can consume the whole answer budget.** At a 100-token
  cap it returned an empty string with no error. See `_effective_cap`.

So the live path uses a non-reasoning model, and reasoning models are kept for
batch work where thinking earns its cost. Never ship learner-facing grammar
feedback on a nano-class model without the evals in docs/10_AI_Design.md §10.8 —
observed contradicting itself on the same sentence across two runs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.errors import (
    ProviderBadRequest,
    ProviderError,
    ProviderRateLimited,
    ProviderRefused,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.ai.ports import Capabilities, Effort, LLMRequest, LLMResponse, Usage
from app.ai.pricing import ModelPrice

logger = logging.getLogger(__name__)

#: Extra `max_completion_tokens` granted to reasoning models so invisible
#: thinking does not consume the answer's budget. See `_effective_cap`.
_REASONING_HEADROOM: dict[Effort, int] = {
    Effort.low: 1024,
    Effort.medium: 2048,
    Effort.high: 4096,
}


class OpenAIProvider:
    """Adapts OpenAI Chat Completions to the ``LLMProvider`` port."""

    def __init__(
        self,
        model: str,
        price: ModelPrice,
        capabilities: Capabilities,
        client: Any,  # openai.AsyncOpenAI — untyped so the SDK stays optional
        max_tokens_field: str = "max_completion_tokens",
        reasoning_model: bool = False,
    ) -> None:
        self.name = f"openai:{model}"
        self.capabilities = capabilities
        self._model = model
        self._price = price
        self._client = client
        # Newer OpenAI models reject `max_tokens` and require
        # `max_completion_tokens`. Which one applies is a per-model fact, so it
        # is set from the catalogue rather than guessed here.
        self._max_tokens_field = max_tokens_field
        # Reasoning models bill invisible thinking against the SAME cap as the
        # answer, so the port's `max_tokens` needs headroom added. See
        # `_effective_cap`.
        self._reasoning_model = reasoning_model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        import openai  # imported lazily so the SDK stays an optional dependency

        kwargs = self._build_kwargs(request)
        started = time.perf_counter()
        try:
            completion = await self._client.chat.completions.create(**kwargs)
        except openai.APITimeoutError as exc:
            raise ProviderTimeout(self.name) from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimited(self.name, _retry_after(exc)) from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailable(self.name, str(exc)) from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailable(self.name, str(exc)) from exc
            raise ProviderBadRequest(self.name, str(exc)) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        choice = completion.choices[0]

        # A safety refusal arrives as HTTP 200 with `message.refusal` set — it
        # does NOT raise. Reading `.content` first would hand the learner a
        # blank suggestion box with no error anywhere.
        refusal = getattr(choice.message, "refusal", None)
        if refusal:
            raise ProviderRefused(self.name, str(refusal))
        if choice.finish_reason == "content_filter":
            raise ProviderRefused(self.name, "content filter")
        text = (choice.message.content or "").strip()

        if choice.finish_reason == "length" and (not text or request.schema is not None):
            # Measured on gpt-5-nano: with a 100-token cap it spent all 100 on
            # reasoning and returned an EMPTY string, finish_reason="length", no
            # exception. Returning that would show the learner a blank box with
            # nothing in the logs. Truncated JSON is equally unusable.
            #
            # Raised as unavailable (retryable) so the chain moves to the next
            # provider rather than aborting — a model with a different reasoning
            # appetite may well answer inside the same budget.
            raise ProviderUnavailable(
                self.name,
                f"output cap reached with {'no' if not text else 'truncated'} visible text "
                f"({usage_reasoning(completion)} reasoning tokens); raise max_tokens",
            )
        parsed = self._parse(request.schema, text) if request.schema is not None else None
        usage = _usage_of(completion)

        return LLMResponse(
            text=text,
            parsed=parsed,
            usage=usage,
            cost_usd=self._price.cost_of(usage),
            model=self._model,
            provider="openai",
            latency_ms=latency_ms,
        )

    # --- request building -------------------------------------------------

    def _build_kwargs(self, request: LLMRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            # Per-request timeout; never mutate the shared client.
            "timeout": request.timeout_s,
            self._max_tokens_field: self._effective_cap(request),
        }

        # Only reasoning models accept this; the others 400 on it. Keeping the
        # rule in `capabilities` means no call site has to know which is which.
        if request.effort in self.capabilities.effort_levels:
            kwargs["reasoning_effort"] = request.effort.value

        if request.schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema.__name__,
                    "schema": to_strict_schema(request.schema),
                    "strict": True,
                },
            }

        # OpenAI caches long prompts automatically above ~1024 tokens; there is
        # no marker to send, so `cache_system` needs no handling here. The
        # discount still shows up in `usage.prompt_tokens_details.cached_tokens`.
        return kwargs

    def _effective_cap(self, request: LLMRequest) -> int:
        """Translate the port's `max_tokens` into OpenAI's `max_completion_tokens`.

        The port means "tokens of answer I want". Anthropic's `max_tokens` means
        the same thing, so it passes straight through. OpenAI **reasoning**
        models bill invisible thinking against the same cap, so a request for
        100 tokens of answer can return nothing at all.

        Measured on gpt-5-nano at `reasoning_effort="low"`: 64-192 reasoning
        tokens for a one-sentence reply. Headroom scales with effort because
        thinking does. Without this the live coach silently returns blank.
        """
        cap = request.max_tokens
        if self._reasoning_model:
            cap += _REASONING_HEADROOM[request.effort]
        return min(cap, self.capabilities.max_output_tokens)

    def _parse(self, schema: type[BaseModel], text: str) -> BaseModel:
        try:
            return schema.model_validate_json(text)
        except ValidationError as exc:
            # Strict mode should make this impossible. If it happens, it is a
            # bad request (our schema), not a transient failure worth retrying.
            raise ProviderBadRequest(self.name, f"schema mismatch: {exc}") from exc


# --- helpers --------------------------------------------------------------


def to_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Render a Pydantic model as a JSON Schema OpenAI strict mode will accept.

    Strict mode has two requirements Pydantic does not meet on its own: every
    object must set ``additionalProperties: false``, and every property must be
    listed in ``required`` (optionality is expressed as a nullable type instead).
    Without this the API rejects the request outright, so the fix belongs here
    rather than in every schema we write.
    """
    schema = model.model_json_schema()
    _tighten(schema)
    return schema


def _tighten(node: Any) -> None:
    """Walk the schema in place, applying strict mode's two rules to each object."""
    if isinstance(node, list):
        for item in node:
            _tighten(item)
        return
    if not isinstance(node, dict):
        return

    if node.get("type") == "object" or "properties" in node:
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["additionalProperties"] = False
            # Strict mode requires EVERY property in `required`. A field that is
            # genuinely optional must be nullable in the model instead.
            node["required"] = list(properties.keys())

    for value in node.values():
        _tighten(value)


def usage_reasoning(completion: Any) -> int:
    """Invisible reasoning tokens billed on this call, when the model reports them."""
    usage = getattr(completion, "usage", None)
    details = getattr(usage, "completion_tokens_details", None) if usage else None
    return (getattr(details, "reasoning_tokens", 0) or 0) if details else 0


def _usage_of(completion: Any) -> Usage:
    """Read token counts defensively — `usage` and its details can be absent."""
    usage = getattr(completion, "usage", None)
    if usage is None:
        return Usage(input_tokens=0, output_tokens=0)
    details = getattr(usage, "prompt_tokens_details", None)
    return Usage(
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        cached_input_tokens=(getattr(details, "cached_tokens", 0) or 0) if details else 0,
    )


def _retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def build_client(api_key: str) -> Any:
    """Create the one shared ``AsyncOpenAI`` for this process.

    ``max_retries=0`` is deliberate. The SDK retries timeouts and 5xx itself, so
    a "3 second" request can take 9 seconds of wall clock — measured: a 3808 ms
    call sailed past a 3.0 s deadline because attempt 1 timed out and attempt 2
    succeeded. In a live room that is a hung UI.

    Retrying is ``FallbackChain``'s job (app/ai/chain.py), which moves to the
    NEXT provider instead of hammering the one that just failed. One retry
    mechanism, not two nested ones with a multiplying deadline.
    """
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ProviderError(
            "openai", "the `openai` package is not installed (`pip install openai`)"
        ) from exc
    return AsyncOpenAI(api_key=api_key, max_retries=0)
