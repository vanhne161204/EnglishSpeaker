"""Shadowing Phase 2 (PRD §8.14): Azure pronunciation checks and their cost.

Offline: a ``FakeAssessor`` stands in for Azure, so these assert our rules —
who may check, how often, what it costs in the ledger, and that names are not
counted — not Azure's scoring.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.ai.errors import ProviderUnavailable
from app.ai.pricing import azure_pronunciation_cost
from app.ai.pronunciation_port import AssessedWord, PronunciationReport
from app.ai.providers.gemini_tts import pcm_to_wav
from app.api.deps import get_assessor
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.ai_usage import AiUsage
from app.models.doc import AnswerTemplate, Doc, DocSection, Question
from app.models.topic import Topic
from app.services.shadowing import name_tokens

ASSESS = "/api/v1/shadowing/assess"
SENTENCE = "I went to Da Nang with my family."
WORDS = [
    ("i", 90.0),
    ("went", 100.0),
    ("to", 90.0),
    ("da", 40.0),
    ("nang", 40.0),
    ("with", 90.0),
    ("my", 100.0),
    ("family", 90.0),
]
#: ai_usage.cost_usd is NUMERIC(12, 8): compare money at the precision it is stored.
CENT_MILLIONTHS = Decimal("0.00000001")


class FakeAssessor:
    name = "azure"
    model = "pronunciation-assessment"
    prosody = True

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    async def assess(self, wav_16k_mono: bytes, reference_text: str) -> PronunciationReport:
        self.calls.append(reference_text)
        if self.fail:
            raise ProviderUnavailable("azure", "down")
        return PronunciationReport(
            accuracy=78.0,
            fluency=95.0,
            completeness=100.0,
            prosody=86.1,
            overall=85.0,
            recognized=reference_text,
            words=[AssessedWord(word, accuracy, "None") for word, accuracy in WORDS],
            provider="azure",
            model=self.model,
        )


def _use(assessor: FakeAssessor | None) -> None:
    app.dependency_overrides[get_assessor] = lambda: assessor


@pytest.fixture
def assessor() -> Iterator[FakeAssessor]:
    fake = FakeAssessor()
    _use(fake)
    yield fake
    app.dependency_overrides.pop(get_assessor, None)


@pytest.fixture(autouse=True)
def limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pronunciation_free_daily", 3)
    monkeypatch.setattr(settings, "pronunciation_premium_daily", 30)
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", 50.0)


def _wav(seconds: float, rate: int = 16_000) -> bytes:
    return pcm_to_wav(b"\x00\x00" * int(rate * seconds), rate)


async def _make_topic(slug: str = "travel") -> tuple[uuid.UUID, str]:
    """A topic whose one answer example is SENTENCE. Returns (topic id, item key)."""
    async with AsyncSessionLocal() as session:
        topic = Topic(slug=slug, title=slug.title(), level="A2")
        session.add(topic)
        await session.flush()
        doc = Doc(topic_id=topic.id, status="published")
        session.add(doc)
        await session.flush()
        section = DocSection(doc_id=doc.id, type="questions", sort_order=0)
        session.add(section)
        await session.flush()
        question = Question(section_id=section.id, text="Where did you go last summer?")
        session.add(question)
        await session.flush()
        answer = AnswerTemplate(
            question_id=question.id, template="I went to ___.", example=SENTENCE
        )
        session.add(answer)
        await session.commit()
        return topic.id, f"answer-{answer.id}"


async def _check(client: AsyncClient, topic_id: uuid.UUID, key: str, wav: bytes | None = None):
    return await client.post(
        ASSESS,
        data={"topic_id": str(topic_id), "item_key": key},
        files={"audio": ("take.wav", wav if wav is not None else _wav(2.0), "audio/wav")},
    )


async def _ledger() -> list[AiUsage]:
    async with AsyncSessionLocal() as session:
        stmt = select(AiUsage).where(AiUsage.task == "pronunciation")
        return list((await session.execute(stmt)).scalars())


def _stored(value: object) -> Decimal:
    return Decimal(str(value)).quantize(CENT_MILLIONTHS)


# --- switched on or off -----------------------------------------------------


async def test_checks_are_off_without_a_key(user_client: AsyncClient) -> None:
    topic_id, key = await _make_topic()
    items = (await user_client.get(f"/api/v1/shadowing/topics/{topic_id}/items")).json()
    assert items["assess_enabled"] is False and items["assess_remaining"] == 0

    resp = await _check(user_client, topic_id, key)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "pronunciation_unavailable"


async def test_items_show_the_checks_left(
    user_client: AsyncClient, assessor: FakeAssessor
) -> None:
    topic_id, _ = await _make_topic()
    items = (await user_client.get(f"/api/v1/shadowing/topics/{topic_id}/items")).json()
    assert items["assess_enabled"] is True and items["assess_remaining"] == 3


# --- a check ----------------------------------------------------------------


async def test_a_check_leaves_names_out_and_is_metered(
    user_client: AsyncClient, assessor: FakeAssessor
) -> None:
    topic_id, key = await _make_topic()
    resp = await _check(user_client, topic_id, key)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert assessor.calls == [SENTENCE]  # scored against the sentence, not free text
    # "Da" and "Nang" (40 each) are not counted: (90+100+90+90+100+90) / 6.
    assert body["accuracy"] == 93.3
    assert {w["word"] for w in body["words"] if w["is_name"]} == {"da", "nang"}
    assert body["prosody"] == 86.1
    assert body["remaining_today"] == 2

    rows = await _ledger()
    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "azure" and row.ok and row.input_tokens == 2
    expected = azure_pronunciation_cost(2.0, prosody=True).quantize(CENT_MILLIONTHS)
    assert _stored(row.cost_usd) == expected


async def test_the_daily_limit(user_client: AsyncClient, assessor: FakeAssessor) -> None:
    topic_id, key = await _make_topic()
    for _ in range(3):
        assert (await _check(user_client, topic_id, key)).status_code == 200
    blocked = await _check(user_client, topic_id, key)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "pronunciation_limit"
    assert len(assessor.calls) == 3


async def test_premium_gets_more_checks(user_client: AsyncClient, assessor: FakeAssessor) -> None:
    await user_client.put("/api/v1/users/me/subscription", json={"plan": "premium"})
    topic_id, _ = await _make_topic()
    items = (await user_client.get(f"/api/v1/shadowing/topics/{topic_id}/items")).json()
    assert items["assess_remaining"] == 30


async def test_a_failed_check_does_not_use_one_up(user_client: AsyncClient) -> None:
    topic_id, key = await _make_topic()
    _use(FakeAssessor(fail=True))
    try:
        resp = await _check(user_client, topic_id, key)
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "pronunciation_failed"
        items = (await user_client.get(f"/api/v1/shadowing/topics/{topic_id}/items")).json()
        assert items["assess_remaining"] == 3
    finally:
        app.dependency_overrides.pop(get_assessor, None)
    # The outage is still in the ledger, at no cost.
    assert [(row.ok, _stored(row.cost_usd)) for row in await _ledger()] == [(False, Decimal(0))]


async def test_audio_must_be_16k_mono_wav(
    user_client: AsyncClient, assessor: FakeAssessor
) -> None:
    topic_id, key = await _make_topic()
    for bad in (_wav(2.0, rate=8_000), b"not a wav file", _wav(31.0), _wav(0.1)):
        resp = await _check(user_client, topic_id, key, wav=bad)
        assert resp.status_code == 400, resp.text
    assert assessor.calls == []


async def test_only_sentences_of_that_topic(
    user_client: AsyncClient, assessor: FakeAssessor
) -> None:
    topic_a, _ = await _make_topic("travel")
    _, key_b = await _make_topic("food")
    resp = await _check(user_client, topic_a, key_b)
    assert resp.status_code == 404
    assert assessor.calls == []


async def test_checks_need_a_user(client: AsyncClient, assessor: FakeAssessor) -> None:
    topic_id, key = await _make_topic()
    assert (await _check(client, topic_id, key)).status_code == 401


# --- helpers and the admin view ---------------------------------------------


def test_names_are_capitalised_words_inside_a_sentence() -> None:
    assert name_tokens(SENTENCE) == {"da", "nang"}
    assert name_tokens("Hello. My name is Minh and I'm from Hue.") == {"minh", "hue"}
    assert name_tokens("Could you say that again?") == set()


def test_azure_cost_per_audio_hour() -> None:
    assert azure_pronunciation_cost(3600, prosody=True) == Decimal("1.30")
    assert azure_pronunciation_cost(3600, prosody=False) == Decimal("1.00")


async def test_admin_sees_spend_per_vendor(admin_client: AsyncClient) -> None:
    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                AiUsage(
                    task="pronunciation",
                    provider="azure",
                    model="pronunciation-assessment",
                    cost_usd=Decimal("0.0016"),
                ),
                AiUsage(
                    task="pronunciation",
                    provider="azure",
                    model="pronunciation-assessment",
                    cost_usd=Decimal("0.0016"),
                ),
                AiUsage(
                    task="shadowing_tts",
                    provider="gemini",
                    model="gemini-3.1-flash-tts-preview",
                    cost_usd=Decimal("0.0019"),
                ),
            ]
        )
        await session.commit()

    resp = await admin_client.get("/api/v1/admin/ai-spend")
    assert resp.status_code == 200, resp.text
    vendors = {row["provider"]: row for row in resp.json()["by_provider"]}
    assert vendors["azure"]["calls"] == 2
    assert Decimal(vendors["azure"]["cost_usd"]) == Decimal("0.0032")
    assert vendors["gemini"]["calls"] == 1
