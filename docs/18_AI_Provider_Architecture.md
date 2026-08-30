<!-- Purpose: Defines the swappable provider architecture for LLM, Speech-to-Text, and Translation engines — the ports, the adapters, the routing table, the resilience wrappers, and the cost accounting that makes the product priceable. Implements ADR #8 in 06_Architecture.md. -->

# 18 AI Provider Architecture

## 18.1 Why this document exists

`06_Architecture.md` ADR #8 already promises:

> **Provider interfaces for STT and LLM** — swap/upgrade providers without product
> code changes.

This document specifies that layer, and **it is now implemented** — see §18.11
for status. The rest of this section records the problem it solved, because the
reasoning is what makes the design reviewable.

Before it, three services each invented their own way to choose an engine, and
none could be changed without a deploy:

| Service | How it used to pick an engine | Problem |
|---|---|---|
| `transcription.py` | `if provider == "deepgram" … elif provider in (…)` | Order hardcoded in the method body |
| `translation.py` | `if provider in ("google", "auto")` chain, methods returning `None` | Different style, same problem |
| `assistant.py` | `if settings.anthropic_api_key: try … except: stub` | No fallback at all, just on/off |

One pattern now replaces all three.

### Six concrete problems it fixed

None of these were hypothetical — all six were in the files:

1. **A new HTTP client per request.** `assistant.py` and `translation.py` both
   call `AsyncAnthropic(api_key=…)` *inside* the request handler. Every AI call
   builds a fresh connection pool and throws it away.
2. **No timeout anywhere.** The Anthropic SDK default is **10 minutes**.
   `10_AI_Design.md` §10.2 requires the live coach to answer in under 2 seconds.
   One slow API call today hangs a room with no ceiling.
3. **Fallback order is hardcoded.** Changing "try Google, then Argos" needs a
   code change, a review, and a deploy.
4. **Model IDs are loose settings.** `translation_model`, `assist_model`, and now
   `feedback_model` — every new AI task adds another top-level setting, and none
   of them know about each other.
5. **`PlanTier` exists but no AI code reads it.** Free and premium users burn
   exactly the same money. There is no margin lever.
6. **No cost is recorded anywhere.** You cannot answer *"what does one premium
   user cost me per month?"* — so you cannot price the product. This is the one
   that blocks going to market.

Fixed at the same time: `06_Architecture.md` §4.1 listed
`claude-haiku-4-5-20251001`. Current model IDs carry **no date suffix** — it is
`claude-haiku-4-5`. That section now points here instead of holding its own copy
of the model list.

---

## 18.2 Three ports, not one

The obvious mistake is to build a single `AIProvider` interface that covers
everything. Do not. Your app swaps **three different kinds** of engine, and they
have nothing in common:

| Port | Job | Implementations |
|---|---|---|
| `LLMProvider` | prompt in → text or validated object out | Anthropic, **OpenAI**, Stub, Fake |
| `Transcriber` | audio in → text out | faster-whisper, Deepgram, Stub |
| `Translator` | text in → text out | Google, Argos, **LLM-backed**, Stub |

Forcing speech-to-text through an LLM interface would mean a `system` prompt
parameter that Deepgram ignores, and an `audio` parameter that Claude rejects.
Three narrow interfaces stay honest; one wide interface becomes a bag of
`None`s.

They share the *pattern* — port, adapters, router, resilience wrappers — not the
*interface*. This document specifies `LLMProvider` in full, then §18.10 shows the
other two, which are the same shape with a different signature.

One useful connection: `Translator` gets an **`LLMTranslator` adapter** that
wraps an `LLMProvider`. That is the Adapter pattern doing its actual job —
making an LLM fit a port it was not designed for — and it replaced the
`_translate_with_claude` method that used to sit inside `translation.py`.

---

## 18.3 The LLM port

```python
# app/ai/ports.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel


class Effort(StrEnum):
    """How hard the model should think. Each adapter maps this to its own knob."""
    low = "low"
    medium = "medium"
    high = "high"


@dataclass(frozen=True, slots=True)
class LLMRequest:
    system: str
    user: str
    max_tokens: int
    # Hard deadline. The live rescue path passes 2.0; a batch report passes 120.
    # There is no default on purpose — forgetting a timeout is how a room hangs.
    timeout_s: float
    effort: Effort = Effort.medium
    # Ask for a validated object instead of text. The adapter uses the provider's
    # native structured output if it has one, and falls back to schema-in-prompt.
    schema: type[BaseModel] | None = None
    # Hint that `system` is large and stable, so it is worth caching. The adapter
    # decides whether that is actually true for its model — see `Capabilities`.
    cache_system: bool = False


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    parsed: BaseModel | None
    usage: Usage
    cost_usd: Decimal          # computed by the adapter from its own price table
    model: str                 # "claude-opus-5"
    provider: str              # "anthropic"
    latency_ms: int
    # True when this came from a fallback, not the first choice. Services can
    # surface a quieter UI; ops can alert when this rate climbs.
    degraded: bool = False


@dataclass(frozen=True, slots=True)
class Capabilities:
    structured_output: bool             # native schema enforcement
    effort_levels: frozenset[Effort]    # EMPTY means "do not send an effort param"
    max_output_tokens: int
    # Prompts shorter than this will not cache, silently. Opus 5 = 512,
    # Haiku 4.5 = 4096. See 10_AI_Design.md §10.2 for why this bites.
    min_cacheable_tokens: int
    accepts_audio: bool                 # false for every Claude model today


class LLMProvider(Protocol):
    """One model behind one call. Every service depends on THIS, never on an SDK."""

    name: str                           # "anthropic:claude-opus-5"
    capabilities: Capabilities

    async def generate(self, request: LLMRequest) -> LLMResponse: ...
```

### Three deliberate omissions

**No `temperature`, `top_p`, or `top_k`.** Claude Opus 5 and Sonnet 5 **removed**
sampling parameters — sending one returns a 400. Putting temperature in a shared
interface would force the Anthropic adapter to silently drop it, which is worse
than not having it: the caller would think they set something. If a future
provider needs it, it becomes that adapter's construction-time config, not part
of the port.

**No `messages` history.** Nothing in this app is a multi-turn chat. Rescue,
translation, sentence check and the IELTS report are all single-shot. Adding a
history parameter that four out of four call sites pass as `[]` is speculative
design. Add it when something needs it.

**No streaming.** The live path returns 3 short sentences; streaming saves
nothing at that size. Add a separate `stream()` method to the port if a
long-output feature arrives.

### Five exceptions — the real value of the adapter

```python
# app/ai/errors.py
class ProviderError(Exception):
    """Base. Anything the adapter could not handle."""

class ProviderTimeout(ProviderError):        """Deadline passed. Retryable."""
class ProviderRateLimited(ProviderError):    """429. Retryable after `retry_after`."""
class ProviderUnavailable(ProviderError):    """5xx or connection failure. Retryable."""
class ProviderRefused(ProviderError):        """Safety refusal. NOT retryable."""
class ProviderBadRequest(ProviderError):     """4xx — our bug. NOT retryable."""
```

Translating each SDK's exception zoo into these five is most of what an adapter
is *for*. Once it is done, the router can decide "try the next provider or give
up" without knowing a thing about Anthropic, and swapping providers does not
change one line of error handling upstream.

---

## 18.4 The Anthropic adapter

The reference implementation. Every other adapter matches this shape.

```python
# app/ai/providers/anthropic_provider.py
import time
import anthropic
from anthropic import AsyncAnthropic

from app.ai.errors import (
    ProviderBadRequest, ProviderRateLimited, ProviderRefused,
    ProviderTimeout, ProviderUnavailable,
)
from app.ai.ports import Capabilities, Effort, LLMRequest, LLMResponse, Usage
from app.ai.pricing import ModelPrice


class AnthropicProvider:
    """Adapts the Anthropic Messages API to the LLMProvider port."""

    def __init__(
        self,
        model: str,
        price: ModelPrice,
        capabilities: Capabilities,
        client: AsyncAnthropic,      # SHARED, built once at app startup
    ) -> None:
        self.name = f"anthropic:{model}"
        self.capabilities = capabilities
        self._model = model
        self._price = price
        self._client = client

    async def generate(self, request: LLMRequest) -> LLMResponse:
        kwargs = self._build_kwargs(request)
        started = time.perf_counter()
        try:
            if request.schema is not None:
                response = await self._client.messages.parse(
                    output_format=request.schema, **kwargs
                )
                parsed = response.parsed_output
            else:
                response = await self._client.messages.create(**kwargs)
                parsed = None
        except anthropic.APITimeoutError as exc:
            raise ProviderTimeout(self.name) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimited(self.name) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailable(self.name) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailable(self.name) from exc
            raise ProviderBadRequest(f"{self.name}: {exc}") from exc

        # A refusal is HTTP 200 with stop_reason="refusal" — it does NOT raise.
        # Check it before reading content, or you hand the learner an empty box.
        if response.stop_reason == "refusal":
            raise ProviderRefused(self.name)

        text = "".join(b.text for b in response.content if b.type == "text").strip()
        usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cached_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        )
        return LLMResponse(
            text=text,
            parsed=parsed,
            usage=usage,
            cost_usd=self._price.cost_of(usage),
            model=self._model,
            provider="anthropic",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def _build_kwargs(self, request: LLMRequest) -> dict:
        system: object = request.system
        # Only mark the cache when the prompt can actually reach this model's
        # minimum. Below it, the marker silently does nothing — no error, no hit.
        if request.cache_system and self._can_cache(request.system):
            system = [{
                "type": "text",
                "text": request.system,
                "cache_control": {"type": "ephemeral"},
            }]

        kwargs: dict = {
            "model": self._model,
            "max_tokens": min(request.max_tokens, self.capabilities.max_output_tokens),
            "system": system,
            "messages": [{"role": "user", "content": request.user}],
            # Per-request override; never mutate the shared client.
            "timeout": request.timeout_s,
        }
        # Haiku 4.5 returns 400 if you send `effort`. The capability set is what
        # keeps that knowledge in ONE place instead of in every call site.
        if request.effort in self.capabilities.effort_levels:
            kwargs["output_config"] = {"effort": request.effort.value}
        return kwargs

    def _can_cache(self, system: str) -> bool:
        # ~4 chars per token is close enough to decide whether to bother.
        return len(system) / 4 >= self.capabilities.min_cacheable_tokens
```

Three things this fixes from the current code, for free:

- **One shared client**, created in the FastAPI lifespan and injected. No more
  pool-per-request.
- **A timeout on every call**, passed per request, never mutating the shared
  client.
- **`stop_reason == "refusal"` is handled.** Today's code reads `.content`
  straight away, so a refusal would produce an empty suggestion with no error.

### Pricing lives with the adapter

```python
# app/ai/pricing.py
from decimal import Decimal

@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    cached_input_per_mtok: Decimal        # ~0.1x input on Anthropic

    def cost_of(self, usage: Usage) -> Decimal:
        m = Decimal(1_000_000)
        fresh = usage.input_tokens - usage.cached_input_tokens
        return (
            Decimal(fresh) * self.input_per_mtok / m
            + Decimal(usage.cached_input_tokens) * self.cached_input_per_mtok / m
            + Decimal(usage.output_tokens) * self.output_per_mtok / m
        )


PRICES: dict[str, ModelPrice] = {
    "claude-opus-5":   ModelPrice(Decimal("5"), Decimal("25"), Decimal("0.5")),
    "claude-sonnet-5": ModelPrice(Decimal("2"), Decimal("10"), Decimal("0.2")),
    "claude-haiku-4-5": ModelPrice(Decimal("1"), Decimal("5"), Decimal("0.1")),
}
```

**Use `Decimal`, never `float`.** This is money that ends up in a billing
report. Also: a stale price table under-reports your costs and quietly wrecks
your margin model, so add a `PRICES_VERIFIED_ON = date(...)` constant and check
it against the pricing page each quarter.

---

## 18.5 The routing table — swap models without a deploy

The adapter makes providers *swappable*. The router is what makes them
*switched*, per task and per paying tier, from configuration.

```python
# app/ai/routing.py
class AiTask(StrEnum):
    rescue         = "rescue"          # 10_AI_Design §10.2 — live, must be fast
    translate      = "translate"       # in-room translator
    sentence_check = "sentence_check"  # §10.3 layer 1
    ielts_report   = "ielts_report"    # §10.3 layer 2


@dataclass(frozen=True, slots=True)
class Route:
    chain: tuple[str, ...]    # provider keys, tried in order; last should be "stub"
    effort: Effort
    max_tokens: int
    timeout_s: float
    cache_system: bool = False
```

Defaults in code, overridable by an `AI_ROUTES` JSON environment variable:

```python
DEFAULT_ROUTES: dict[tuple[AiTask, PlanTier], Route] = {
    # Live path. Cheap, fast, and NO retry — a retry doubles the wait in a call.
    (AiTask.rescue, PlanTier.free): Route(
        chain=("anthropic:claude-haiku-4-5", "stub"),
        effort=Effort.medium, max_tokens=400, timeout_s=2.0,
    ),
    (AiTask.rescue, PlanTier.premium): Route(
        chain=("anthropic:claude-haiku-4-5", "stub"),
        effort=Effort.medium, max_tokens=400, timeout_s=2.5,
    ),

    # Sentence check. Free tier gets the cheaper model; premium gets accuracy.
    (AiTask.sentence_check, PlanTier.free): Route(
        chain=("anthropic:claude-sonnet-5", "stub"),
        effort=Effort.medium, max_tokens=8000, timeout_s=90.0,
    ),
    (AiTask.sentence_check, PlanTier.premium): Route(
        chain=("anthropic:claude-opus-5", "anthropic:claude-sonnet-5", "stub"),
        effort=Effort.medium, max_tokens=8000, timeout_s=90.0,
    ),

    # The band report. Premium gets high effort — it is a judgement call.
    (AiTask.ielts_report, PlanTier.free): Route(
        chain=("anthropic:claude-sonnet-5", "stub"),
        effort=Effort.medium, max_tokens=8000, timeout_s=120.0, cache_system=True,
    ),
    (AiTask.ielts_report, PlanTier.premium): Route(
        chain=("anthropic:claude-opus-5", "anthropic:claude-sonnet-5", "stub"),
        effort=Effort.high, max_tokens=8000, timeout_s=120.0, cache_system=True,
    ),
}
```

Now *"margins are thin this month, move free-tier reports to Haiku"* is an
environment variable and a container restart. Not a code review and a release.

**The chain must always end in `"stub"`.** The existing services already degrade
to a labelled stub rather than crash, and that behaviour is correct — a live room
must never die because an API is down. The chain makes that a property of the
configuration instead of a `try/except` repeated in three files.

---

## 18.6 Resilience wrappers

Each of these *is* an `LLMProvider` and *wraps* an `LLMProvider`, so they compose
in any order. Adapter handles "which vendor"; these handle "what if it goes
wrong" and "what did it cost".

### FallbackChain — the one with real logic

```python
class FallbackChain:
    def __init__(self, providers: Sequence[LLMProvider]) -> None:
        self._providers = tuple(providers)
        self.name = " → ".join(p.name for p in providers)
        self.capabilities = providers[0].capabilities

    async def generate(self, request: LLMRequest) -> LLMResponse:
        last_error: Exception | None = None
        for index, provider in enumerate(self._providers):
            try:
                response = await provider.generate(request)
                return response if index == 0 else replace(response, degraded=True)
            except (ProviderTimeout, ProviderRateLimited, ProviderUnavailable) as exc:
                last_error = exc
                logger.warning("%s failed (%s), trying next", provider.name, type(exc).__name__)
            except ProviderBadRequest:
                # Our request is malformed. It will fail identically on the next
                # provider — falling through just burns latency and hides the bug.
                raise
            except ProviderRefused as exc:
                last_error = exc          # a different model may well answer
        raise AllProvidersFailed(self.name) from last_error
```

The distinction in those three `except` clauses is the whole point: **retry
transient failures, never retry your own bad request.** A 400 falling through a
three-provider chain turns one fast error into three slow ones and buries the
real cause.

### MeteredProvider — the one that makes the business work

```python
class MeteredProvider:
    """Records what every call cost. This is what makes the product priceable."""

    def __init__(self, inner: LLMProvider, sink: UsageSink,
                 user_id: uuid.UUID, task: AiTask, room_id: uuid.UUID | None) -> None:
        ...

    async def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            response = await self._inner.generate(request)
        except Exception:
            await self._sink.record_failure(self._user_id, self._task)
            raise
        await self._sink.record(
            user_id=self._user_id, task=self._task, room_id=self._room_id,
            provider=response.provider, model=response.model,
            usage=response.usage, cost_usd=response.cost_usd,
            latency_ms=response.latency_ms, degraded=response.degraded,
        )
        return response
```

Write the row **outside** the request's DB transaction, or a rolled-back
business transaction erases the record of money you actually spent.

### Others

| Wrapper | What it does | Where |
|---|---|---|
| `BudgetGuard` | Refuses when the user's daily or the org's monthly cap is hit. Raises a typed error the API turns into a friendly message. | Outermost |
| `RetryProvider` | One retry on `ProviderRateLimited`, honouring `retry_after`. **Never on the live path.** | Batch routes only |
| `CachedProvider` | Content-hash lookup before calling (`10_AI_Design.md` §10.3.3). | Sentence check only |

### Composition

```python
def build_llm(task: AiTask, tier: PlanTier, user_id: uuid.UUID, sink: UsageSink,
              room_id: uuid.UUID | None = None) -> LLMProvider:
    route = ROUTES[(task, tier)]
    chain = FallbackChain([REGISTRY[key] for key in route.chain])
    return BudgetGuard(MeteredProvider(chain, sink, user_id, task, room_id), user_id)
```

Order matters and reads outside-in: *check the budget → record the cost → try
each provider in turn.* Metering sits inside the guard so a refused call is not
billed, and outside the chain so a fallback's cost is still counted.

---

## 18.7 What the services become

`AssistantService` today constructs an SDK client, builds provider-specific
kwargs, and owns a `try/except → stub`. After this change it owns none of that:

```python
class AssistantService:
    def __init__(self, llm: LLMProvider, docs: DocRepository | None = None) -> None:
        self._llm = llm
        self._docs = docs

    async def assist(self, payload: AssistRequest) -> AssistResult:
        trusted = await self._topic_context(payload)
        response = await self._llm.generate(LLMRequest(
            system=build_rescue_system(payload.kind, payload.level, trusted),
            user=build_rescue_user(payload),
            max_tokens=400,
            timeout_s=2.0,
            schema=Suggestions,
        ))
        return AssistResult(
            suggestions=response.parsed.items,
            kind=payload.kind,
            provider=response.provider,
            degraded=response.degraded,
        )
```

No SDK import. No key check. No fallback logic. No model name. Two payoffs:

1. **Tests need no API key and no network.** Inject a `FakeProvider` that returns
   a canned `LLMResponse`, or one that raises `ProviderTimeout`, and assert the
   service behaves. Today you cannot unit-test `AssistantService` at all without
   either a live key or monkey-patching the SDK.
2. **The eval harness in `10_AI_Design.md` §10.8 becomes trivial** — point the
   registry at a different model, re-run, compare. That is what "eval-gated model
   swap" (§18.9) needs to be cheap enough to actually do.

Wiring in `deps.py` stays the same shape you already use:

```python
def get_assistant_service(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AssistantService:
    llm = build_llm(AiTask.rescue, user.plan_tier, user.id, UsageSink(session))
    return AssistantService(llm, DocRepository(session))
```

---

## 18.8 The `ai_usage` table — the number that decides your price

```python
class AiUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_usage"

    user_id: FK users.id ON DELETE CASCADE, index
    room_id: FK rooms.id ON DELETE SET NULL, nullable
    task:     String(24), index      # rescue | translate | sentence_check | ielts_report
    provider: String(24)
    model:    String(48), index

    input_tokens:  Integer
    output_tokens: Integer
    cached_tokens: Integer
    cost_usd:      Numeric(10, 6)    # NOT Float. Six decimals: calls cost ~$0.0016.
    latency_ms:    Integer
    degraded:      Boolean, default False
    ok:            Boolean, default True
```

Index `(user_id, created_at)` and `(created_at, task)`. Keep 13 months, then roll
up to monthly totals and delete the rows — this table grows faster than anything
else in the schema.

Four queries you will run constantly:

```sql
-- 1. Cost per user last 30 days. This is your COGS. Everything else follows.
SELECT user_id, SUM(cost_usd) FROM ai_usage
WHERE created_at > now() - interval '30 days' GROUP BY user_id ORDER BY 2 DESC;

-- 2. Which feature is eating the budget?
SELECT task, SUM(cost_usd), COUNT(*), AVG(latency_ms) FROM ai_usage
WHERE created_at > now() - interval '7 days' GROUP BY task ORDER BY 2 DESC;

-- 3. Is the primary provider healthy? A rising degraded rate is an early warning.
SELECT model, AVG(degraded::int), AVG(ok::int) FROM ai_usage
WHERE created_at > now() - interval '1 day' GROUP BY model;

-- 4. p95 latency on the live path. 10_AI_Design §10.2 promises under 2 seconds.
SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)
FROM ai_usage WHERE task = 'rescue' AND created_at > now() - interval '1 day';
```

Migration: `alembic/versions/0016_ai_usage.py`.

---

## 18.9 Adapting to the market

### The free tier is what kills you, not the premium tier

Using the costs from `10_AI_Design.md` §10.9, at 4 sessions per user per month:

| Tier | Routing | Cost / user / month |
|---|---|---|
| **Premium** — Opus 5, everything on | rescue + layer 1 + layer 2 | **~$0.92** |
| **Free** — Sonnet 5, 2 reports/month, layer 1 only | rescue + capped layer 1 | **~$0.18** |
| Free with **no caps** (today's behaviour) | same as premium | **~$0.92** |

Premium at $0.92 is comfortable: priced at $5/month that is **18% COGS**, which
leaves room for infrastructure and payment fees.

The free tier is the trap. A thousand free users at today's uncapped routing is
**$920 a month against zero revenue**. Capped and routed to Sonnet it is $180.
The routing table in §18.5 is not a nice-to-have — it is the difference between
a free tier you can afford and one that ends the company.

Three caps to enforce in `BudgetGuard`, not in scattered endpoint checks:

- Free: 2 IELTS reports per week, 30 rescue taps per day.
- Premium: 30 reports per week, 200 rescue taps per day — high enough that no
  real learner notices, low enough to stop a scripted abuser.
- Org-wide monthly ceiling with an alert at 70%. A bug that loops an API call
  should cost you a Slack message, not a month of runway.

### A paywall that does not cripple the free product

The free tier should feel *good* and still leave a reason to pay. From
`10_AI_Design.md` §10.3.14:

| | Free | Premium |
|---|---|---|
| Rescue Me in the room | ✅ Yes, this is the hook | ✅ |
| Band scores + summary | ✅ | ✅ |
| **The 3 blockers and 3 drills** | ❌ Locked | ✅ |
| IELTS Part 2 cue-card mode | ❌ | ✅ |
| Band history chart | Last 3 | All |

Give away the *diagnosis*, charge for the *treatment*. A learner who sees
"Band 5.5, and here are three specific things holding you back — unlock to see
them" converts far better than one who was never shown a band at all. Never
paywall Rescue Me: it is the feature that makes someone come back tomorrow.

### Vendor risk

Today one provider outage takes down rescue, translation, and feedback at once.
After this change, the chain degrades — and adding a second vendor is one new
adapter file plus one line in `AI_ROUTES`, with no service code touched.

Build the second adapter **before** you need it. Writing your first alternative
adapter during an outage is how you find out the port was wrong.

### Never swap a model without running the evals

`10_AI_Design.md` §10.8 defines two eval sets: the 60-sentence gold set and the
20-transcript band calibration set. Make passing both a **release gate** for any
routing change:

```
1. Change AI_ROUTES in staging.
2. Run the sentence eval        → recall > 85%, false positives < 5%.
3. Run the band calibration     → MAE ≤ 0.5, signed error within ±0.25.
4. Compare cost/session from ai_usage.
5. Only then change production.
```

A cheaper model that inflates bands by half a point is not a saving. It is a
refund request and a bad review, and you will not find out for a month. The
`model` column already exists on `sentence_feedback`, `session_reports`, and
`ai_usage`, so you can always answer "which model produced this?" after the fact.

### The kill switch

Add `ai_enabled: bool = True`. When false, `build_llm` returns the stub chain for
every task. The app keeps working — rooms, voice, chat, transcripts all run —
and only the AI extras go quiet. You want this to exist *before* the incident
where you need it.

---

## 18.10 The other two ports

Same pattern, different signatures. Both replace the ad-hoc dispatch described
in §18.1.

```python
class Transcriber(Protocol):
    name: str
    async def transcribe(self, audio: bytes, language: str | None) -> Transcript: ...
    # Adapters: FasterWhisperTranscriber, DeepgramTranscriber,
    #           GroqWhisperTranscriber, StubTranscriber

class Translator(Protocol):
    name: str
    async def translate(self, text: str, source: str | None, target: str) -> Translation: ...
    # Adapters: GoogleTranslator, ArgosTranslator, LLMTranslator, StubTranslator
```

`LLMTranslator` is the interesting one — it takes an `LLMProvider` in its
constructor and adapts it to the `Translator` port:

```python
class LLMTranslator:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def translate(self, text: str, source: str | None, target: str) -> Translation:
        response = await self._llm.generate(LLMRequest(
            system=build_translate_system(source, target),
            user=text, max_tokens=1024, timeout_s=10.0,
        ))
        return Translation(text=response.text, provider=response.provider)
```

That single class replaces `_translate_with_claude` in `translation.py`, and it
inherits the fallback chain, the metering and the budget guard for free —
translation costs land in `ai_usage` alongside everything else, with no extra
code.

Note that `Transcriber` gets metered too, but into a separate table or with
`task='transcribe'` — Deepgram bills per audio minute, not per token, so its
`ModelPrice` equivalent takes seconds rather than tokens. Do not force per-token
pricing onto an engine that does not bill that way.

---

## 18.11 Migration status

**Steps 1-5 are done** (2026-08-29). The record below keeps the reasoning, and
notes what measurement changed along the way.

| # | Step | Status |
|---|---|---|
| 1 | Ports, adapters, errors, pricing, registry | **Done** — `app/ai/` |
| 2 | Shared clients + a timeout on every call | **Done** |
| 3 | `ai_usage` + `MeteredProvider` + `BudgetGuard` | **Done** — migration `0014_ai_usage` |
| 4 | `AssistantService` on the port | **Done** — `/api/v1/assist` returns `provider=openai` |
| 5 | Translation + transcription on their ports | **Done** — `TranslatorChain`, `TranscriberChain` |
| 6 | Routing table + spend caps | **Done** — `app/ai/routing.py`, `AI_ROUTES` |

159 tests, all offline: `conftest.py` forces `AI_ENABLED=false` so the suite
never touches a live API. The two scripts that do are run by hand:
`scripts/check_ai_provider.py` and `scripts/run_feedback_eval.py`.

### Four things measurement changed

Each of these contradicted a reasonable assumption, and each is now a comment
next to the code it affects.

1. **The cheapest model by list price was the most expensive in practice.**
   `gpt-5-nano` lists at $0.05/1M input against `gpt-4o-mini`'s $0.15 — but it is
   a reasoning model that bills 100-200 invisible thinking tokens to write one
   sentence, making it **~5x dearer per short call**. It is also slower
   (1.75s-5.7s vs 1.3s). The live path uses `gpt-4o-mini`.
2. **Reasoning tokens can eat the entire answer budget.** At a 100-token cap
   `gpt-5-nano` spent all 100 thinking and returned an **empty string** with
   `finish_reason="length"` and no exception. `OpenAIProvider._effective_cap`
   adds headroom; an empty answer from a hit cap now raises.
3. **SDK retries multiply the timeout.** A 3808 ms call sailed past a 3.0 s
   deadline because the SDK retried internally — wall clock is
   `timeout x (max_retries+1)`. Both clients are built with `max_retries=0`;
   `FallbackChain` owns retry, and it moves to the *next* provider.
4. **A model can pass recall and still be unusable.** `gpt-4o-mini` scored 11/30
   false positives on the grammar gold set, "correcting" 7 of the 10 garbled
   speech-to-text lines. `gpt-5-mini` scored 100% recall / 0% false positives.
   Model choice for `sentence_check` is gated on
   `scripts/run_feedback_eval.py`, not on price.

### Known gaps

* **Deepgram spend is not in `ai_usage`.** It bills per audio minute, not per
  token, so it does not pass through `MeteredProvider`. Add a duration-based
  price entry when transcription volume matters; `Transcript.duration_s` is
  already captured for it.
* **`TranslationService` and `TranscriptionService` are not budget-capped.**
  Only LLM-backed translation is, because it borrows the LLM stack. Google and
  Argos are effectively free; Deepgram is not, and would need its own guard.
* **`settings.translation_model` is now unused** by the service and can be
  removed once nothing references it.

## 18.12 What NOT to abstract

Abstractions cost something. These are deliberately out of scope:

- **A universal wrapper for every provider feature.** The port covers what this
  app does: a system prompt, a user prompt, text or a validated object back.
  Anything else — tool use, vision, multi-turn, MCP — stays behind a capability
  flag or does not exist until a feature needs it.
- **A plugin loader.** Adapters are Python classes in one dict. Runtime plugin
  discovery buys nothing when the whole list fits on one screen.
- **A prompt-templating framework.** `app/services/prompts.py` with f-strings is
  correct at this size. Prompts change more often than the code around them, so
  keep them readable and reviewable in a diff.
- **Provider-agnostic prompts.** Prompts *are* model-specific — that is why the
  eval gate in §18.9 exists. Do not chase one prompt that scores equally on every
  model; you will land on the worst of all of them.
- **Streaming, until something needs it.** See §18.3.

The test for adding anything here: *"Do I have two real implementations of this
today?"* If not, it is a guess about the future, and guesses about the future are
what make abstractions leak.
