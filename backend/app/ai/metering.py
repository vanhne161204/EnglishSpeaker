"""Cost recording and spend caps (docs §18.6).

Both are ``LLMProvider`` decorators, so they compose with the fallback chain and
with each other. Wiring order is outside-in:

    BudgetGuard( MeteredProvider( FallbackChain([...]) ) )

which reads as *check the budget -> record what it cost -> try each provider*.
Metering sits inside the guard so a refused call is not billed, and outside the
chain so a fallback's cost is still counted.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.ai.errors import ProviderError
from app.ai.ports import LLMProvider, LLMRequest, LLMResponse
from app.ai.routing import AiTask
from app.core.config import settings
from app.models.ai_usage import AiUsage
from app.models.enums import PlanTier
from app.repositories.ai_usage import AiUsageRepository

logger = logging.getLogger(__name__)


class BudgetExceeded(ProviderError):
    """A cap was hit. Carries a message the API can show the learner as-is."""

    retryable = False


class UsageSink:
    """Writes one ``ai_usage`` row per call.

    The write is committed on its **own** session, separate from the request's
    business transaction. If the caller later rolls back — a failed room update,
    a validation error — the record of money actually spent must survive.
    """

    def __init__(self, session_factory=None) -> None:
        if session_factory is None:
            from app.db.session import AsyncSessionLocal

            session_factory = AsyncSessionLocal
        self._session_factory = session_factory

    async def record(self, usage: AiUsage) -> None:
        try:
            async with self._session_factory() as session:
                await AiUsageRepository(session).add(usage)
                await session.commit()
        except Exception:  # noqa: BLE001 — telemetry must never break a live call
            logger.exception(
                "Failed to record AI usage (task=%s model=%s)", usage.task, usage.model
            )


class MeteredProvider:
    """Records what every call cost. This is what makes the product priceable."""

    def __init__(
        self,
        inner: LLMProvider,
        sink: UsageSink,
        task: AiTask,
        user_id: uuid.UUID | None = None,
        room_id: uuid.UUID | None = None,
    ) -> None:
        self.name = inner.name
        self.capabilities = inner.capabilities
        self._inner = inner
        self._sink = sink
        self._task = task
        self._user_id = user_id
        self._room_id = room_id

    async def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            response = await self._inner.generate(request)
        except ProviderError as exc:
            # A failed call still costs latency and may have cost tokens. Record
            # it so an outage is visible in the data rather than as silence.
            await self._sink.record(
                AiUsage(
                    user_id=self._user_id,
                    room_id=self._room_id,
                    task=self._task.value,
                    provider=getattr(exc, "provider", "unknown"),
                    model="unknown",
                    ok=False,
                )
            )
            raise

        await self._sink.record(
            AiUsage(
                user_id=self._user_id,
                room_id=self._room_id,
                task=self._task.value,
                provider=response.provider,
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cached_tokens=response.usage.cached_input_tokens,
                cost_usd=response.cost_usd,
                latency_ms=response.latency_ms,
                degraded=response.degraded,
                ok=True,
            )
        )
        return response


#: Calls per user per day, by tier. Premium limits are set high enough that no
#: real learner notices, low enough to stop a scripted abuser (docs §18.9).
DAILY_CALL_CAPS: dict[tuple[AiTask, PlanTier], int] = {
    (AiTask.rescue, PlanTier.free): 30,
    (AiTask.rescue, PlanTier.premium): 200,
    (AiTask.translate, PlanTier.free): 100,
    (AiTask.translate, PlanTier.premium): 500,
    (AiTask.sentence_check, PlanTier.free): 4,
    (AiTask.sentence_check, PlanTier.premium): 40,
    (AiTask.ielts_report, PlanTier.free): 2,
    (AiTask.ielts_report, PlanTier.premium): 30,
}

_FRIENDLY: dict[AiTask, str] = {
    AiTask.rescue: "coaching suggestions",
    AiTask.translate: "translations",
    AiTask.sentence_check: "sentence feedback",
    AiTask.ielts_report: "practice reports",
}


class BudgetGuard:
    """Refuses a call when a per-user daily cap or the org monthly cap is hit.

    Centralised on purpose: scattering "have they used too much?" across
    endpoints is how one path ends up unmetered and a bug runs up the bill.
    """

    def __init__(
        self,
        inner: LLMProvider,
        task: AiTask,
        tier: PlanTier,
        user_id: uuid.UUID | None,
        repo_factory=None,
    ) -> None:
        self.name = inner.name
        self.capabilities = inner.capabilities
        self._inner = inner
        self._task = task
        self._tier = tier
        self._user_id = user_id
        if repo_factory is None:
            from app.db.session import AsyncSessionLocal

            repo_factory = AsyncSessionLocal
        self._session_factory = repo_factory

    async def generate(self, request: LLMRequest) -> LLMResponse:
        await self._check()
        return await self._inner.generate(request)

    async def _check(self) -> None:
        cap = DAILY_CALL_CAPS.get((self._task, self._tier))
        now = datetime.now(UTC)

        try:
            async with self._session_factory() as session:
                repo = AiUsageRepository(session)

                # Org-wide monthly ceiling: the backstop against a looping bug.
                monthly = await repo.spend_since(now - timedelta(days=30))
                ceiling = Decimal(str(settings.ai_monthly_budget_usd))
                if ceiling > 0 and monthly >= ceiling:
                    logger.error(
                        "AI monthly budget exhausted: $%s of $%s", monthly, ceiling
                    )
                    raise BudgetExceeded(
                        "budget",
                        "AI features are paused for now. Please try again later.",
                    )
                if ceiling > 0 and monthly >= ceiling * Decimal("0.7"):
                    logger.warning(
                        "AI spend at %.0f%% of the monthly budget ($%s of $%s)",
                        float(monthly / ceiling * 100),
                        monthly,
                        ceiling,
                    )

                if cap is None or self._user_id is None:
                    return
                used = await repo.call_count_since(
                    now - timedelta(days=1), self._user_id, self._task.value
                )
        except BudgetExceeded:
            raise
        except Exception:  # noqa: BLE001 — a metering outage must not block learning
            logger.exception("Budget check failed; allowing the call through")
            return

        if used >= cap:
            raise BudgetExceeded(
                "budget",
                f"You have used your {_FRIENDLY[self._task]} for today "
                f"({used}/{cap}). They reset in 24 hours.",
            )
