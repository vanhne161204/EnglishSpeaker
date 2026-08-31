"""Coach Report layer 1 (docs/10_AI_Design.md §10.3).

Most of these test how the service AVOIDS calling the model. The filter and the
hash cache do more for the bill than any model choice (§10.3.3), and a silent
regression in either would double the cost of the feature without failing
anything else.

Offline throughout: a ``FakeProvider`` stands in for the model.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.ai.errors import ProviderTimeout
from app.ai.metering import BudgetExceeded
from app.ai.providers.stub import FakeProvider
from app.ai.routing import AiTask, get_route
from app.db.session import AsyncSessionLocal
from app.models.enums import PlanTier
from app.models.transcript import TranscriptSegment
from app.repositories.feedback import FeedbackRepository
from app.schemas.feedback import FeedbackBatch, GrammarError, SentenceVerdict
from app.services.feedback import (
    BATCH_SIZE,
    FeedbackService,
    chunk,
    normalise,
    select_segments,
    text_hash,
    worth_assessing,
)

ROUTE = get_route(AiTask.sentence_check, PlanTier.free)


def _segment(text: str, room_id=None, user_id=None) -> TranscriptSegment:
    return TranscriptSegment(
        id=uuid.uuid4(),
        room_id=room_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        speaker_name="Lan",
        text=text,
        spoken_at=datetime.now(UTC),
    )


def _verdict(index: int, *, wrong: bool = True) -> SentenceVerdict:
    return SentenceVerdict(
        index=index,
        errors=(
            [GrammarError(wrong="go", right="went", kind="verb tense", why="past")]
            if wrong
            else []
        ),
        vocab=[],
        is_correct=not wrong,
        corrected="I went there." if wrong else None,
        natural="I went there.",
        paraphrase="I travelled there.",
        cefr="B1",
        score=70,
    )


def _provider(count: int, **kw) -> FakeProvider:
    """A model that returns one verdict per input sentence."""
    return FakeProvider(parsed=FeedbackBatch(items=[_verdict(i) for i in range(count)]), **kw)


# --- the filter: the cheapest saving there is (§10.3.3) -------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("I went to Da Nang last weekend.", True),
        ("yeah", False),
        ("ok", False),
        ("I think so", False),  # a whole-line filler
        ("Yes.", False),
        ("I like it", False),  # 3 words: under the floor
        ("I like it very much", True),
        ("   ", False),
        # The filler list matches whole lines only — this is a real sentence.
        ("I think so because it helps me relax after work", True),
    ],
)
def test_only_gradeable_lines_survive_the_filter(text, expected) -> None:
    assert worth_assessing(text) is expected


def test_a_repeated_sentence_is_graded_once_per_session() -> None:
    seen: set[str] = set()
    assert worth_assessing("I go to school every day", seen) is True
    assert worth_assessing("I go to school every day.", seen) is False  # punctuation
    assert worth_assessing("i GO to School every day", seen) is False  # case


def test_normalising_makes_the_same_sentence_hash_the_same() -> None:
    assert text_hash("I go there.") == text_hash("i go there")
    assert text_hash("I go there") != text_hash("I went there")
    assert normalise("Hello,  WORLD!!") == "hello world"


def test_the_filter_removes_roughly_half_a_real_session() -> None:
    """The §10.3.3 claim that drives the cost model."""
    session = [
        "yeah", "I went to Da Nang last weekend.", "ok", "It was really beautiful",
        "me too", "We stayed near the beach for three days", "right",
        "The food there is much better than in my city", "I think so", "sure",
    ]
    kept = select_segments([_segment(t) for t in session])
    assert len(kept) == 4  # 10 in, 4 worth paying for


# --- batching (§10.3.4) ---------------------------------------------------


def test_sentences_are_batched_not_sent_one_by_one() -> None:
    """60 sentences must become 3 calls, not 60."""
    segments = [_segment(f"This is sentence number {i} of the session") for i in range(60)]
    batches = list(chunk(segments))
    assert len(batches) == 3
    assert all(len(b) <= BATCH_SIZE for b in batches)


async def test_one_api_call_covers_a_whole_batch() -> None:
    user_id = uuid.uuid4()
    segments = [_segment(f"I go to the shop on day {i} every week") for i in range(5)]
    provider = _provider(5)

    async with AsyncSessionLocal() as session:
        service = FeedbackService(provider, ROUTE, FeedbackRepository(session))
        rows = await service.assess(user_id, segments)
        await session.commit()

    assert len(provider.calls) == 1
    assert len(rows) == 5


# --- the hash cache (§10.3.3) --------------------------------------------


async def test_a_sentence_already_graded_is_not_paid_for_twice() -> None:
    user_id = uuid.uuid4()
    segments = [_segment("I go to the market every Sunday morning")]

    async with AsyncSessionLocal() as session:
        service = FeedbackService(_provider(1), ROUTE, FeedbackRepository(session))
        await service.assess(user_id, segments)
        await session.commit()

    # Same sentence, said again in a later session.
    repeat = _provider(1)
    async with AsyncSessionLocal() as session:
        service = FeedbackService(repeat, ROUTE, FeedbackRepository(session))
        rows = await service.assess(user_id, [_segment("I go to the market every Sunday morning")])
        await session.commit()

    assert repeat.calls == []  # no API call at all
    assert len(rows) == 1  # but the learner still gets their feedback


async def test_the_cache_is_scoped_to_one_learner() -> None:
    """Feedback is phrased for a learner's level, so sharing it across users
    would hand a B2 speaker advice written for an A2 one."""
    text = "I go to the market every Sunday morning"
    async with AsyncSessionLocal() as session:
        await FeedbackService(_provider(1), ROUTE, FeedbackRepository(session)).assess(
            uuid.uuid4(), [_segment(text)]
        )
        await session.commit()

    other = _provider(1)
    async with AsyncSessionLocal() as session:
        await FeedbackService(other, ROUTE, FeedbackRepository(session)).assess(
            uuid.uuid4(), [_segment(text)]
        )
        await session.commit()

    assert len(other.calls) == 1  # a different learner pays for their own


# --- correctness ----------------------------------------------------------


async def test_the_learners_level_reaches_the_prompt() -> None:
    provider = _provider(1)
    async with AsyncSessionLocal() as session:
        service = FeedbackService(provider, ROUTE, FeedbackRepository(session))
        await service.assess(
            uuid.uuid4(), [_segment("I go there every single day")], level="advanced"
        )
        await session.commit()

    # "advanced" is a room/user word; the prompt needs a CEFR band.
    assert "C1" in provider.calls[0].system


async def test_the_sentences_are_numbered_so_verdicts_can_be_matched_back() -> None:
    provider = _provider(2)
    segments = [_segment("First full sentence here"), _segment("Second full sentence here")]
    async with AsyncSessionLocal() as session:
        service = FeedbackService(provider, ROUTE, FeedbackRepository(session))
        await service.assess(uuid.uuid4(), segments)
        await session.commit()

    assert "0. First full sentence here" in provider.calls[0].user
    assert "1. Second full sentence here" in provider.calls[0].user


async def test_an_out_of_range_index_is_dropped_not_mis_attached() -> None:
    """A shifted index would attach feedback to the wrong sentence — worse than
    no feedback, because the learner would 'correct' something they said fine."""
    bad = FakeProvider(parsed=FeedbackBatch(items=[_verdict(0), _verdict(99)]))
    async with AsyncSessionLocal() as session:
        service = FeedbackService(bad, ROUTE, FeedbackRepository(session))
        rows = await service.assess(uuid.uuid4(), [_segment("Only one sentence here today")])
        await session.commit()

    assert len(rows) == 1


async def test_the_stored_row_carries_which_model_produced_it() -> None:
    async with AsyncSessionLocal() as session:
        service = FeedbackService(_provider(1), ROUTE, FeedbackRepository(session))
        rows = await service.assess(uuid.uuid4(), [_segment("I go there every single day")])
        await session.commit()

    assert rows[0].model  # needed to answer "why was this feedback poor?"


# --- degradation ----------------------------------------------------------


async def test_a_provider_failure_returns_what_was_gathered_not_an_error() -> None:
    async with AsyncSessionLocal() as session:
        service = FeedbackService(
            FakeProvider(raises=ProviderTimeout("fake")), ROUTE, FeedbackRepository(session)
        )
        rows = await service.assess(uuid.uuid4(), [_segment("I go there every single day")])
        await session.commit()
    assert rows == []


async def test_a_spend_cap_stops_cleanly() -> None:
    async with AsyncSessionLocal() as session:
        service = FeedbackService(
            FakeProvider(raises=BudgetExceeded("budget", "capped")),
            ROUTE,
            FeedbackRepository(session),
        )
        rows = await service.assess(uuid.uuid4(), [_segment("I go there every single day")])
        await session.commit()
    assert rows == []


async def test_a_provider_with_no_structured_output_does_not_store_junk() -> None:
    """The stub cannot invent a schema instance; storing nothing beats storing
    a row that claims the learner's English was assessed when it wasn't."""
    async with AsyncSessionLocal() as session:
        service = FeedbackService(FakeProvider(text="hi"), ROUTE, FeedbackRepository(session))
        rows = await service.assess(uuid.uuid4(), [_segment("I go there every single day")])
        await session.commit()
    assert rows == []


async def test_nothing_gradeable_costs_nothing() -> None:
    provider = _provider(0)
    async with AsyncSessionLocal() as session:
        service = FeedbackService(provider, ROUTE, FeedbackRepository(session))
        rows = await service.assess(uuid.uuid4(), [_segment("yeah"), _segment("ok")])
    assert rows == []
    assert provider.calls == []


# --- endpoints ------------------------------------------------------------


async def test_feedback_endpoints_need_authentication(client: AsyncClient) -> None:
    for path in ("/api/v1/feedback/me", "/api/v1/feedback/me/summary"):
        assert (await client.get(path)).status_code == 401


async def test_assessing_a_session_with_no_speech_says_so(client: AsyncClient) -> None:
    auth = (
        await client.post(
            "/api/v1/auth/register",
            json={"username": f"fb{uuid.uuid4().hex[:8]}", "password": "pw12345678"},
        )
    ).json()
    room = (
        await client.post(
            "/api/v1/rooms",
            json={"title": "Quiet", "mode": "normal"},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
    ).json()

    resp = await client.post(
        f"/api/v1/feedback/rooms/{room['id']}",
        headers={"Authorization": f"Bearer {auth['token']}"},
    )

    assert resp.status_code == 400
    body = resp.json()["error"]  # {"error": {"code", "message"}} — app-wide shape
    assert body["code"] == "nothing_to_assess"
    assert "didn't say anything" in body["message"].lower()


async def test_the_summary_counts_repeated_mistakes(client: AsyncClient) -> None:
    """The view a learner actually returns for — and it costs no AI call."""
    auth = (
        await client.post(
            "/api/v1/auth/register",
            json={"username": f"fb{uuid.uuid4().hex[:8]}", "password": "pw12345678"},
        )
    ).json()
    user_id = uuid.UUID(auth["user"]["id"])

    async with AsyncSessionLocal() as session:
        service = FeedbackService(_provider(3), ROUTE, FeedbackRepository(session))
        await service.assess(
            user_id,
            [
                _segment("I go to the shop yesterday morning"),
                _segment("She go to the park last night"),
                _segment("They go to the beach last summer"),
            ],
        )
        await session.commit()

    resp = await client.get(
        "/api/v1/feedback/me/summary", headers={"Authorization": f"Bearer {auth['token']}"}
    )

    body = resp.json()
    assert body["sentences_checked"] == 3
    assert body["with_errors"] == 3
    assert body["top_mistakes"][0] == {"kind": "verb tense", "count": 3}
