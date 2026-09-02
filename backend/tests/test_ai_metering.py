"""Tests for cost recording, spend caps, and routing (docs §18.5, §18.6).

Offline: a ``FakeProvider`` stands in for the model, so these assert our own
accounting rather than a vendor's behaviour.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.ai.errors import ProviderTimeout
from app.ai.metering import (
    DAILY_CALL_CAPS,
    BudgetExceeded,
    BudgetGuard,
    MeteredProvider,
    UsageSink,
)
from app.ai.ports import Effort, LLMRequest
from app.ai.providers.stub import FakeProvider
from app.ai.routing import DEFAULT_ROUTES, LLM_TASKS, AiTask, get_route
from app.db.session import AsyncSessionLocal
from app.models.ai_usage import AiUsage
from app.models.enums import PlanTier
from app.repositories.ai_usage import AiUsageRepository


def _request() -> LLMRequest:
    return LLMRequest(system="s", user="u", max_tokens=100, timeout_s=5.0)


async def _spend_rows() -> list[AiUsage]:
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        return list((await session.execute(select(AiUsage))).scalars())


# --- routing --------------------------------------------------------------


def test_every_task_and_tier_combination_has_a_route() -> None:
    """A missing entry would KeyError at request time, in a live room.

    Only LLM tasks: `transcription` bills per audio minute and never touches a
    model chain (see `routing.LLM_TASKS`).
    """
    for task in LLM_TASKS:
        for tier in PlanTier:
            assert (task, tier) in DEFAULT_ROUTES, f"no route for {task}:{tier}"


def test_the_live_rescue_path_uses_a_non_reasoning_model() -> None:
    """Measured: gpt-5-nano is slower AND ~5x dearer per short call than
    gpt-4o-mini, because reasoning tokens bill as output. The live path must not
    pick a reasoning model by accident."""
    route = get_route(AiTask.rescue, PlanTier.free)
    assert "gpt-5-nano" not in route.chain[0]
    # Observed max latency was 1991 ms on gpt-4o-mini; 2.0s would flap.
    assert route.timeout_s >= 3.0


def test_batch_routes_get_far_longer_timeouts_than_the_live_one() -> None:
    assert get_route(AiTask.ielts_report, PlanTier.premium).timeout_s >= 60
    assert get_route(AiTask.rescue, PlanTier.free).timeout_s <= 5


def test_premium_gets_a_stronger_model_than_free_for_reports() -> None:
    free = get_route(AiTask.ielts_report, PlanTier.free)
    premium = get_route(AiTask.ielts_report, PlanTier.premium)
    assert free.chain != premium.chain
    assert premium.effort is Effort.high


def test_ai_routes_env_override_patches_one_field_only(monkeypatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.settings, "ai_routes", '{"rescue:free": {"timeout_s": 9.5}}')
    route = get_route(AiTask.rescue, PlanTier.free)
    assert route.timeout_s == 9.5
    # Untouched fields keep their defaults — a patch is not a replacement.
    assert route.chain == DEFAULT_ROUTES[(AiTask.rescue, PlanTier.free)].chain


def test_malformed_ai_routes_is_ignored_not_fatal(monkeypatch) -> None:
    """A typo in an env var must not stop the API from starting."""
    from app.core import config

    monkeypatch.setattr(config.settings, "ai_routes", "{not json")
    assert get_route(AiTask.rescue, PlanTier.free).timeout_s == 3.0


# --- metering -------------------------------------------------------------


async def test_a_successful_call_is_recorded_with_its_cost() -> None:
    provider = MeteredProvider(
        FakeProvider(cost_usd=Decimal("0.000123")), UsageSink(), AiTask.rescue
    )
    await provider.generate(_request())

    rows = await _spend_rows()
    assert len(rows) == 1
    assert rows[0].task == "rescue"
    assert Decimal(str(rows[0].cost_usd)) == Decimal("0.000123")
    assert rows[0].ok is True


async def test_a_failed_call_is_still_recorded() -> None:
    """A provider that is timing out constantly is an outage worth seeing."""
    provider = MeteredProvider(
        FakeProvider(raises=ProviderTimeout("fake")), UsageSink(), AiTask.rescue
    )
    with pytest.raises(ProviderTimeout):
        await provider.generate(_request())

    rows = await _spend_rows()
    assert len(rows) == 1
    assert rows[0].ok is False


async def test_six_decimal_places_survive_the_round_trip() -> None:
    """A rescue call costs ~$0.000011. Float or NUMERIC(x,3) would store zero."""
    await MeteredProvider(
        FakeProvider(cost_usd=Decimal("0.00001100")), UsageSink(), AiTask.rescue
    ).generate(_request())

    rows = await _spend_rows()
    assert Decimal(str(rows[0].cost_usd)) > 0


# --- budget guard ---------------------------------------------------------


async def _seed_calls(user_id: uuid.UUID, task: AiTask, count: int) -> None:
    async with AsyncSessionLocal() as session:
        repo = AiUsageRepository(session)
        for _ in range(count):
            await repo.add(
                AiUsage(
                    user_id=user_id,
                    task=task.value,
                    provider="fake",
                    model="fake",
                    cost_usd=Decimal("0.000001"),
                )
            )
        await session.commit()


async def test_under_the_cap_the_call_goes_through() -> None:
    user_id = uuid.uuid4()
    guard = BudgetGuard(FakeProvider(), AiTask.rescue, PlanTier.free, user_id)
    assert (await guard.generate(_request())).text == "ok"


async def test_the_daily_cap_is_enforced_per_user_and_task(make_user) -> None:
    user_id = await make_user()
    cap = DAILY_CALL_CAPS[(AiTask.rescue, PlanTier.free)]
    await _seed_calls(user_id, AiTask.rescue, cap)

    guard = BudgetGuard(FakeProvider(), AiTask.rescue, PlanTier.free, user_id)
    with pytest.raises(BudgetExceeded) as excinfo:
        await guard.generate(_request())
    # The message is shown to the learner as-is, so it must read like English.
    assert "today" in str(excinfo.value)


async def test_one_users_spend_does_not_cap_another(make_user) -> None:
    heavy, light = await make_user("Heavy"), await make_user("Light")
    await _seed_calls(heavy, AiTask.rescue, DAILY_CALL_CAPS[(AiTask.rescue, PlanTier.free)])

    guard = BudgetGuard(FakeProvider(), AiTask.rescue, PlanTier.free, light)
    assert (await guard.generate(_request())).text == "ok"


async def test_caps_are_per_task_not_shared(make_user) -> None:
    """Using up rescue taps must not lock the learner out of feedback too."""
    user_id = await make_user()
    await _seed_calls(user_id, AiTask.rescue, DAILY_CALL_CAPS[(AiTask.rescue, PlanTier.free)])

    guard = BudgetGuard(FakeProvider(), AiTask.ielts_report, PlanTier.free, user_id)
    assert (await guard.generate(_request())).text == "ok"


async def test_premium_gets_a_higher_cap_than_free() -> None:
    for task in LLM_TASKS:
        assert DAILY_CALL_CAPS[(task, PlanTier.premium)] > DAILY_CALL_CAPS[(task, PlanTier.free)]


async def test_the_org_monthly_ceiling_stops_everyone(monkeypatch) -> None:
    """The backstop against a looping bug — not a per-user limit."""
    from app.core import config

    async with AsyncSessionLocal() as session:
        await AiUsageRepository(session).add(
            AiUsage(task="rescue", provider="fake", model="fake", cost_usd=Decimal("9.99"))
        )
        await session.commit()

    monkeypatch.setattr(config.settings, "ai_monthly_budget_usd", 5.0)
    guard = BudgetGuard(FakeProvider(), AiTask.rescue, PlanTier.free, uuid.uuid4())
    with pytest.raises(BudgetExceeded):
        await guard.generate(_request())


async def test_spend_outside_the_window_does_not_count() -> None:
    from sqlalchemy import update

    from app.core import config

    async with AsyncSessionLocal() as session:
        row = AiUsage(task="rescue", provider="fake", model="fake", cost_usd=Decimal("9.99"))
        await AiUsageRepository(session).add(row)
        await session.execute(
            update(AiUsage)
            .where(AiUsage.id == row.id)
            .values(created_at=datetime.now(UTC) - timedelta(days=40))
        )
        await session.commit()

    config.settings.ai_monthly_budget_usd = 5.0
    try:
        guard = BudgetGuard(FakeProvider(), AiTask.rescue, PlanTier.free, uuid.uuid4())
        assert (await guard.generate(_request())).text == "ok"
    finally:
        config.settings.ai_monthly_budget_usd = 50.0


async def test_a_metering_outage_does_not_block_learning(monkeypatch) -> None:
    """If the ledger is unreadable, let the call through rather than break a room."""

    class _Broken:
        def __call__(self):
            raise RuntimeError("db down")

    guard = BudgetGuard(
        FakeProvider(), AiTask.rescue, PlanTier.free, uuid.uuid4(), repo_factory=_Broken()
    )
    assert (await guard.generate(_request())).text == "ok"
