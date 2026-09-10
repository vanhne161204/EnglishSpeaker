"""AI voice coach (PRD §8.12): allowance, token minting, and server-side time.

Offline: a ``FakeMinter`` stands in for Gemini, so these assert our own rules —
who may start, for how long, and what gets recorded — not Google's behaviour.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.ai.errors import ProviderUnavailable
from app.ai.live_port import LiveToken, LiveTokenRequest
from app.ai.pricing import gemini_live_cost
from app.api.deps import get_live_token_minter
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.ai_usage import AiUsage
from app.models.topic import Topic
from app.models.voice_session import AiVoiceSession
from app.services.voice_coach import build_coach_instruction

SESSIONS = "/api/v1/voice-coach/sessions"
USAGE = "/api/v1/voice-coach/usage"


class FakeMinter:
    name = "fake"
    model = "gemini-3.1-flash-live-preview"

    def __init__(self, *, fail: bool = False) -> None:
        self.requests: list[LiveTokenRequest] = []
        self.fail = fail

    async def mint(self, request: LiveTokenRequest) -> LiveToken:
        self.requests.append(request)
        if self.fail:
            raise ProviderUnavailable("gemini", "down")
        return LiveToken(
            token=f"auth_tokens/fake-{len(self.requests)}", model=self.model, provider="gemini"
        )


def _use(minter: FakeMinter | None) -> None:
    app.dependency_overrides[get_live_token_minter] = lambda: minter


@pytest.fixture
def minter() -> Iterator[FakeMinter]:
    fake = FakeMinter()
    _use(fake)
    yield fake
    app.dependency_overrides.pop(get_live_token_minter, None)


@pytest.fixture(autouse=True)
def limits(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pin the numbers these tests reason about, whatever a local .env says.
    monkeypatch.setattr(settings, "voice_coach_free_daily_seconds", 900)
    monkeypatch.setattr(settings, "voice_coach_premium_daily_seconds", 3600)
    monkeypatch.setattr(settings, "voice_coach_session_max_seconds", 600)
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", 50.0)


async def _ledger() -> list[AiUsage]:
    async with AsyncSessionLocal() as session:
        stmt = select(AiUsage).where(AiUsage.task == "voice_coach")
        return list((await session.execute(stmt)).scalars())


# --- access -----------------------------------------------------------------


async def test_start_requires_sign_in(client: AsyncClient, minter: FakeMinter) -> None:
    resp = await client.post(SESSIONS, json={})
    assert resp.status_code == 401
    assert minter.requests == []


async def test_coach_is_off_without_a_key(user_client: AsyncClient) -> None:
    # conftest forces AI_ENABLED=false, so the real minter is never built.
    usage = await user_client.get(USAGE)
    assert usage.status_code == 200, usage.text
    assert usage.json()["enabled"] is False

    resp = await user_client.post(SESSIONS, json={})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "voice_coach_unavailable"


# --- starting a session -----------------------------------------------------


async def test_start_returns_a_one_use_token_with_a_hard_end(
    user_client: AsyncClient, minter: FakeMinter
) -> None:
    resp = await user_client.post(SESSIONS, json={})
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["token"] == "auth_tokens/fake-1"
    assert body["model"] == minter.model
    assert body["max_seconds"] == 600
    # 900 a day, 600 held by this session.
    assert body["remaining_seconds"] == 300

    # The end time goes INTO the token, so Gemini itself stops the session.
    request = minter.requests[0]
    left = (request.expires_at - datetime.now(UTC)).total_seconds()
    assert 590 <= left <= 600
    assert "everyday small talk" in request.system_instruction


async def test_topic_title_and_level_reach_the_coach(
    user_client: AsyncClient, minter: FakeMinter
) -> None:
    async with AsyncSessionLocal() as session:
        topic = Topic(slug="travel", title="Travel", level="B1")
        session.add(topic)
        await session.commit()
        topic_id = topic.id

    resp = await user_client.post(SESSIONS, json={"topic_id": str(topic_id)})
    assert resp.status_code == 201, resp.text
    assert resp.json()["topic_title"] == "Travel"
    instruction = minter.requests[0].system_instruction
    assert '"Travel"' in instruction
    assert "B1" in instruction


async def test_unknown_topic_is_404(user_client: AsyncClient, minter: FakeMinter) -> None:
    resp = await user_client.post(SESSIONS, json={"topic_id": str(uuid.uuid4())})
    assert resp.status_code == 404
    assert minter.requests == []


def test_instruction_lists_the_questions_in_order() -> None:
    text = build_coach_instruction(
        "Travel", "A2", ["Where did you go last summer?", "What did you eat there?"]
    )
    assert "1. Where did you go last summer?" in text
    assert "2. What did you eat there?" in text
    assert text.index("1. Where") < text.index("2. What")


# --- the allowance ----------------------------------------------------------


async def test_an_open_session_holds_its_full_limit(
    user_client: AsyncClient, minter: FakeMinter
) -> None:
    """Two tabs must not both spend the same minutes."""
    first = await user_client.post(SESSIONS, json={})
    assert first.json()["max_seconds"] == 600

    second = await user_client.post(SESSIONS, json={})
    assert second.status_code == 201, second.text
    assert second.json()["max_seconds"] == 300
    assert second.json()["remaining_seconds"] == 0

    third = await user_client.post(SESSIONS, json={})
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "voice_coach_limit"
    assert "already have" in third.json()["error"]["message"]

    # The learner is shown time actually used, not time held.
    usage = (await user_client.get(USAGE)).json()
    assert usage["used_seconds"] <= 2


async def test_premium_gets_the_premium_allowance(
    user_client: AsyncClient, minter: FakeMinter
) -> None:
    await user_client.put("/api/v1/users/me/subscription", json={"plan": "premium"})
    usage = (await user_client.get(USAGE)).json()
    assert usage["daily_limit_seconds"] == 3600


# --- ending a session -------------------------------------------------------


async def test_ending_gives_back_unused_time_and_records_the_cost(
    user_client: AsyncClient, minter: FakeMinter
) -> None:
    session_id = (await user_client.post(SESSIONS, json={})).json()["id"]

    resp = await user_client.post(f"{SESSIONS}/{session_id}/end")
    assert resp.status_code == 200, resp.text
    ended = resp.json()
    assert ended["used_seconds"] <= 2
    assert ended["remaining_seconds"] >= 898

    # Ending twice is safe and changes nothing.
    again = (await user_client.post(f"{SESSIONS}/{session_id}/end")).json()
    assert again["used_seconds"] == ended["used_seconds"]

    rows = await _ledger()
    assert len(rows) == 1
    assert rows[0].provider == "gemini" and rows[0].ok

    # With the first session closed, a new one gets the full cap again.
    fresh = await user_client.post(SESSIONS, json={})
    assert fresh.json()["max_seconds"] == 600


async def test_cannot_end_someone_elses_session(
    user_client: AsyncClient, other_client: AsyncClient, minter: FakeMinter
) -> None:
    session_id = (await user_client.post(SESSIONS, json={})).json()["id"]
    resp = await other_client.post(f"{SESSIONS}/{session_id}/end")
    assert resp.status_code == 404


async def test_an_abandoned_session_counts_in_full(
    user_client: AsyncClient, minter: FakeMinter
) -> None:
    """The tab closed without calling "end": the token was usable until expiry."""
    session_id = (await user_client.post(SESSIONS, json={})).json()["id"]

    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        row = await session.get(AiVoiceSession, uuid.UUID(session_id))
        assert row is not None
        row.created_at = now - timedelta(minutes=20)
        row.expires_at = now - timedelta(minutes=10)
        await session.commit()

    usage = (await user_client.get(USAGE)).json()
    assert usage["used_seconds"] == 600
    assert usage["remaining_seconds"] == 300

    rows = await _ledger()
    assert len(rows) == 1
    assert Decimal(str(rows[0].cost_usd)) == gemini_live_cost(minter.model, 600)


# --- failure paths ----------------------------------------------------------


async def test_a_failed_token_request_uses_no_minutes(user_client: AsyncClient) -> None:
    _use(FakeMinter(fail=True))
    try:
        resp = await user_client.post(SESSIONS, json={})
    finally:
        app.dependency_overrides.pop(get_live_token_minter, None)

    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "voice_coach_failed"
    async with AsyncSessionLocal() as session:
        assert (await session.execute(select(AiVoiceSession))).first() is None
    # The outage is still visible in the ledger.
    assert [row.ok for row in await _ledger()] == [False]


async def test_monthly_budget_pauses_the_coach(
    user_client: AsyncClient, minter: FakeMinter
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            AiUsage(task="rescue", provider="openai", model="gpt-4o-mini", cost_usd=Decimal("60"))
        )
        await session.commit()

    resp = await user_client.post(SESSIONS, json={})
    assert resp.status_code == 503
    assert minter.requests == []


# --- pricing ----------------------------------------------------------------


def test_ten_minutes_costs_about_thirteen_cents() -> None:
    # 600 s x 25 tok/s = 15,000 tokens in at $3/M, 7,500 out at $12/M.
    assert gemini_live_cost("gemini-3.1-flash-live-preview", 600) == Decimal("0.135")
    # An unpriced model must not look free.
    assert gemini_live_cost("some-future-model", 600) == Decimal("0.135")
