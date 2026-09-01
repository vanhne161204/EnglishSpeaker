"""Every paid AI call leaves a row, and the row says what it cost (docs §18.8).

The point of this file is coverage of the *channels*, not of one adapter. A spend
dashboard that silently misses a channel is worse than no dashboard: it reads as
authoritative and is wrong. Translation and speech-to-text were both unmetered
until now — $0 today because their default engines are free, and a trap the day
either paid engine is switched on.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai.errors import ProviderUnavailable
from app.ai.metering import MeteredTranscriber, MeteredTranslator, UsageSink
from app.ai.ports import Usage
from app.ai.pricing import PRICES, ModelPrice, deepgram_cost, google_translate_cost
from app.ai.routing import LLM_TASKS, AiTask
from app.ai.stt_port import Transcript
from app.ai.translate_port import TranslateJob, Translation
from app.db.session import AsyncSessionLocal
from app.models.ai_usage import AiUsage


async def _rows() -> list[AiUsage]:
    async with AsyncSessionLocal() as session:
        return list(
            (await session.execute(select(AiUsage).order_by(AiUsage.created_at))).scalars().all()
        )


class _FakeTranslator:
    name = "fake"

    def __init__(self, provider: str = "google") -> None:
        self._provider = provider

    async def translate(self, job: TranslateJob) -> Translation:
        return Translation(
            text="xin chao " * 3, target_lang=job.target_lang, provider=self._provider
        )


class _FailingTranslator:
    name = "fake"

    async def translate(self, job: TranslateJob) -> Translation:
        raise ProviderUnavailable("google", "down")


class _FakeTranscriber:
    name = "fake"

    def __init__(self, provider: str, duration_s: float | None) -> None:
        self._provider = provider
        self._duration = duration_s

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        return Transcript(
            text="hello there", language="en", provider=self._provider, duration_s=self._duration
        )


# --- the arithmetic ---------------------------------------------------------


def test_token_cost_charges_cached_input_at_the_discount() -> None:
    """Cached input is ~10x cheaper. Billing it at the full rate would overstate
    the cost of exactly the calls prompt caching was added to make cheap."""
    price = ModelPrice(Decimal("1.00"), Decimal("10.00"), Decimal("0.10"))
    usage = Usage(input_tokens=1_000, output_tokens=100, cached_input_tokens=800)

    # 200 fresh @ $1 + 800 cached @ $0.10 + 100 out @ $10, per 1M.
    expected = (Decimal(200) * 1 + Decimal(800) * Decimal("0.10") + Decimal(100) * 10) / 1_000_000
    assert price.cost_of(usage) == expected


def test_prices_are_decimals_not_floats() -> None:
    """A float price silently poisons every downstream sum. $0.000011 per call
    is small enough that binary rounding error is not academic."""
    for model, price in PRICES.items():
        for field in (price.input_per_mtok, price.output_per_mtok, price.cached_input_per_mtok):
            assert isinstance(field, Decimal), model


def test_translation_and_stt_are_not_priced_per_token() -> None:
    """They bill per character and per audio minute. Forcing them through the
    token table would put a plausible, wrong number in the ledger."""
    assert google_translate_cost(1_000_000) == Decimal("20.00")
    assert deepgram_cost(3600) == Decimal("0.0043") * 60


def test_zero_and_missing_durations_cost_nothing() -> None:
    assert deepgram_cost(None) == 0
    assert deepgram_cost(0) == 0


# --- every channel writes a row ---------------------------------------------


async def test_a_translation_writes_one_row(monkeypatch) -> None:
    """Translation was the paid path with no ledger entry at all."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "google_translate_api_key", "fake-key")
    metered = MeteredTranslator(_FakeTranslator(), UsageSink(), user_id=None)

    await metered.translate(TranslateJob(text="hello world", target_lang="vi"))

    rows = await _rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.task == AiTask.translation.value
    assert row.provider == "google"
    assert row.ok is True
    # Characters in, priced per million.
    assert row.input_tokens == len("hello world")
    assert Decimal(str(row.cost_usd)) == google_translate_cost(len("hello world"))


async def test_translation_without_an_api_key_is_recorded_at_zero(monkeypatch) -> None:
    """Google's free endpoint is not billed. Recording a phantom charge would be
    worse than recording nothing — it would overstate the cost of the free tier."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "google_translate_api_key", None)
    metered = MeteredTranslator(_FakeTranslator(), UsageSink())

    await metered.translate(TranslateJob(text="hello world", target_lang="vi"))

    rows = await _rows()
    assert len(rows) == 1
    assert Decimal(str(rows[0].cost_usd)) == 0
    assert rows[0].ok is True  # still recorded: volume matters even when free


async def test_a_local_translation_engine_is_recorded_at_zero() -> None:
    """Argos runs on this machine. No invoice, but the row still shows the call
    happened — a spike in volume is a signal even when the price is zero."""
    metered = MeteredTranslator(_FakeTranslator(provider="argos"), UsageSink())
    await metered.translate(TranslateJob(text="hello", target_lang="vi"))

    rows = await _rows()
    assert len(rows) == 1
    assert rows[0].provider == "argos"
    assert Decimal(str(rows[0].cost_usd)) == 0


async def test_a_failed_translation_is_recorded_as_failed() -> None:
    """An outage should be visible in the data, not as silence."""
    metered = MeteredTranslator(_FailingTranslator(), UsageSink())
    with pytest.raises(ProviderUnavailable):
        await metered.translate(TranslateJob(text="hi", target_lang="vi"))

    rows = await _rows()
    assert len(rows) == 1
    assert rows[0].ok is False
    assert rows[0].provider == "google"


async def test_deepgram_transcription_is_billed_per_audio_minute() -> None:
    """Per MINUTE, from the duration the engine reports — not per token."""
    metered = MeteredTranscriber(_FakeTranscriber("deepgram", duration_s=120.0), UsageSink())
    await metered.transcribe(b"audio")

    rows = await _rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.task == "transcription"
    assert row.provider == "deepgram"
    assert row.input_tokens == 120  # seconds of audio
    assert Decimal(str(row.cost_usd)) == deepgram_cost(120.0)


async def test_local_whisper_is_recorded_at_zero() -> None:
    """No invoice, but it burns CPU on a 2 GB box — worth seeing the volume."""
    metered = MeteredTranscriber(_FakeTranscriber("whisper", duration_s=30.0), UsageSink())
    await metered.transcribe(b"audio")

    rows = await _rows()
    assert Decimal(str(rows[0].cost_usd)) == 0
    assert rows[0].provider == "whisper"


# --- the ledger and the summary agree ---------------------------------------


async def test_the_summary_totals_match_the_individual_rows(admin_client) -> None:
    """The overview is an aggregate of the ledger. If they disagree, one of them
    is lying and there is no way to tell which."""
    costs = [Decimal("0.000011"), Decimal("0.020000"), Decimal("0.001500")]
    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                AiUsage(task="rescue", provider="openai", model="gpt-4o-mini", cost_usd=c)
                for c in costs
            ]
        )
        await session.commit()

    summary = (await admin_client.get("/api/v1/admin/ai-spend")).json()
    ledger = (await admin_client.get("/api/v1/admin/ai-calls")).json()

    assert Decimal(summary["today_usd"]) == sum(costs)
    assert summary["calls"] == 3
    assert len(ledger["items"]) == 3
    assert sum(Decimal(r["cost_usd"]) for r in ledger["items"]) == sum(costs)


async def test_the_ledger_is_newest_first_and_filterable(admin_client) -> None:
    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                AiUsage(task="rescue", provider="openai", model="a", cost_usd=Decimal("0.01")),
                AiUsage(
                    task="ielts_report", provider="openai", model="b", cost_usd=Decimal("0.02")
                ),
                AiUsage(task="rescue", provider="openai", model="c", ok=False),
            ]
        )
        await session.commit()

    everything = (await admin_client.get("/api/v1/admin/ai-calls")).json()["items"]
    assert everything[0]["model"] == "c", "newest first"

    only_rescue = (
        await admin_client.get("/api/v1/admin/ai-calls", params={"task": "rescue"})
    ).json()["items"]
    assert {r["model"] for r in only_rescue} == {"a", "c"}

    failures = (
        await admin_client.get("/api/v1/admin/ai-calls", params={"failed_only": True})
    ).json()["items"]
    assert [r["model"] for r in failures] == ["c"]


async def test_the_daily_series_fills_in_quiet_days(admin_client) -> None:
    """A chart that skips days with no calls compresses time and makes a spike
    look like a plateau."""
    async with AsyncSessionLocal() as session:
        session.add(
            AiUsage(
                task="rescue",
                provider="openai",
                model="gpt-4o-mini",
                cost_usd=Decimal("0.05"),
                created_at=datetime.now(UTC) - timedelta(days=3),
            )
        )
        await session.commit()

    body = (await admin_client.get("/api/v1/admin/ai-spend", params={"days": 7})).json()
    days = body["by_day"]

    assert len(days) == 7, "one point per day, including empty ones"
    assert [d["day"] for d in days] == sorted(d["day"] for d in days), "oldest first"
    assert sum(Decimal(d["cost_usd"]) for d in days) == Decimal("0.05")
    assert sum(1 for d in days if Decimal(d["cost_usd"]) == 0) == 6


async def test_per_user_cost_carries_a_real_call_count(admin_client) -> None:
    """`calls` was hardcoded to 0 — a field that lied. Cost alone cannot tell a
    heavy user from one expensive call."""
    me = (await admin_client.get("/api/v1/users/me")).json()["id"]
    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                AiUsage(
                    user_id=uuid.UUID(me),
                    task="rescue",
                    provider="openai",
                    model="gpt-4o-mini",
                    cost_usd=Decimal("0.001"),
                )
                for _ in range(4)
            ]
        )
        await session.commit()

    by_user = (await admin_client.get("/api/v1/admin/ai-spend")).json()["by_user"]
    assert len(by_user) == 1
    assert by_user[0]["calls"] == 4
    assert Decimal(by_user[0]["cost_usd"]) == Decimal("0.004")


# --- the tables cannot drift apart ------------------------------------------


def test_every_llm_task_has_a_daily_cap() -> None:
    """An uncapped task is an unbounded bill."""
    from app.ai.metering import DAILY_CALL_CAPS
    from app.models.enums import PlanTier

    for task in LLM_TASKS:
        for tier in PlanTier:
            assert (task, tier) in DAILY_CALL_CAPS, f"no cap for {task}:{tier}"


def test_transcription_is_deliberately_outside_the_llm_router() -> None:
    """It takes audio bytes and bills per minute; no model chain applies."""
    assert AiTask.transcription not in LLM_TASKS
