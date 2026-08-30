"""Coach Report layer 2 — the IELTS band report (docs §10.3.7-10.3.14).

Three groups matter most:

* **Rounding** — `round()` gets IELTS wrong, silently, on every report.
* **Privacy** — a partner's words must never reach a report about someone else,
  and that is enforced in code, not by a prompt rule.
* **Honesty** — pronunciation is not scored, and the overall must say so.
"""

from __future__ import annotations

import statistics
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.ai.errors import ProviderTimeout
from app.ai.metering import BudgetExceeded
from app.ai.providers.stub import FakeProvider
from app.ai.routing import AiTask, get_route
from app.db.session import AsyncSessionLocal
from app.models.enums import PlanTier
from app.models.transcript import TranscriptSegment
from app.repositories.session_report import SessionReportRepository
from app.schemas.ielts import (
    Blocker,
    Criterion,
    CriterionScore,
    Drill,
    IeltsReport,
    ReportMode,
)
from app.services import speech_metrics
from app.services.bands import clamp, next_band, overall_band
from app.services.ielts import IeltsService, NotEnoughSpeech, ReportUnavailable
from app.services.ielts_context import build_turns, render_turns, strip_foreign_quotes

ROUTE = get_route(AiTask.ielts_report, PlanTier.free)
BASE = datetime(2026, 8, 30, 10, 0, 0, tzinfo=UTC)


def _seg(text: str, user_id: uuid.UUID, offset_s: float = 0.0) -> TranscriptSegment:
    return TranscriptSegment(
        id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        user_id=user_id,
        speaker_name="Lan",
        text=text,
        spoken_at=BASE + timedelta(seconds=offset_s),
    )


def _criterion(band: float, evidence: list[str]) -> CriterionScore:
    return CriterionScore(
        evidence=evidence,
        what_worked="Clear ideas.",
        what_held_back="Short turns.",
        descriptor="willing to speak at length",
        band=band,
    )


def _report(bands=(6.0, 6.5, 6.0), evidence: list[str] | None = None) -> IeltsReport:
    quotes = evidence if evidence is not None else ["I went to Da Nang last weekend"]
    return IeltsReport(
        fluency=_criterion(bands[0], quotes),
        lexical=_criterion(bands[1], quotes),
        grammar=_criterion(bands[2], quotes),
        summary="Good ideas, short answers.",
        blockers=[
            Blocker(
                title="Answers are too short",
                example="Yes, I like it.",
                fix="Yes, I like it because it helps me relax.",
                criterion=Criterion.fluency,
            )
        ],
        drills=[Drill(title="Use because", how="Answer 5 questions with because.", minutes=10)],
    )


# --- band arithmetic: the bug everyone ships ------------------------------


def test_ielts_rounds_a_quarter_band_UP_not_to_even() -> None:
    """`round(6.25 * 2) / 2` gives 6.0 in Python — half a band too low, on every
    report, with nothing failing."""
    assert overall_band(6.0, 6.5, 6.0, 6.5) == Decimal("6.5")  # mean 6.25
    assert round(6.25 * 2) / 2 == 6.0  # what the naive version would have given


def test_three_quarters_rounds_up_to_the_whole_band() -> None:
    assert overall_band(7.0, 6.5, 7.0, 6.5) == Decimal("7.0")  # mean 6.75


@pytest.mark.parametrize(
    "bands,expected",
    [
        ((6.0, 6.0, 6.0), "6.0"),
        ((5.0, 6.0, 6.0), "5.5"),  # 5.666 -> 5.5
        ((6.0, 6.0, 7.0), "6.5"),  # 6.333 -> 6.5
        ((5.5, 6.0, 6.5), "6.0"),
        ((9.0, 9.0, 9.0), "9.0"),
    ],
)
def test_three_criterion_averages(bands, expected) -> None:
    assert overall_band(*bands) == Decimal(expected)


def test_bands_stay_inside_the_scale() -> None:
    assert clamp(12) == Decimal("9")
    assert clamp(-3) == Decimal("0")
    assert clamp(6.3) == Decimal("6.5")  # snapped to a half step
    assert next_band(9.0) == Decimal("9")  # cannot exceed the top


def test_overall_band_rejects_an_empty_call() -> None:
    with pytest.raises(ValueError):
        overall_band()


# --- measured metrics (§10.3.8) -------------------------------------------


def test_metrics_measure_pauses_and_turn_length_from_timestamps() -> None:
    """You cannot see hesitation in text; you can see it in timestamps."""
    me = uuid.uuid4()
    segments = [
        _seg("I went to the market yesterday with my mother", me, 0),
        _seg("We bought some fruit and vegetables there", me, 2),  # continuous
        _seg("It was quite cheap actually", me, 20),  # long pause before
    ]
    m = speech_metrics.compute(segments)

    assert m.turn_count == 3
    assert m.long_pause_count == 1
    assert m.longest_turn_words == 9  # "I went to the market yesterday with my mother"
    assert m.total_words == 21


def test_fillers_and_self_corrections_are_counted() -> None:
    me = uuid.uuid4()
    m = speech_metrics.compute(
        [_seg("um I went there uh I mean I went to the shop you know", me, 0)]
    )
    assert m.filler_rate > 0
    assert m.self_correction_count >= 1


def test_subordination_is_what_separates_simple_from_complex() -> None:
    me = uuid.uuid4()
    simple = speech_metrics.compute([_seg("I like coffee it is nice", me, 0)])
    complex_ = speech_metrics.compute(
        [_seg("I like coffee because it helps me focus when I work", me, 0)]
    )
    assert simple.complex_clause_ratio == 0.0
    assert complex_.complex_clause_ratio == 1.0


def test_metrics_on_an_empty_session_do_not_explode() -> None:
    m = speech_metrics.compute([])
    assert m.total_words == 0
    assert m.words_per_minute == 0.0


def test_an_unmeasurable_rate_is_reported_as_unmeasurable() -> None:
    """Segments finalised in a burst cannot give a real rate. Saying so beats
    quoting a figure the model will reason from — the same principle that keeps
    pronunciation unscored."""
    me = uuid.uuid4()
    burst = [
        _seg("a really long sentence with many words in it here", me, i * 0.01)
        for i in range(10)
    ]
    m = speech_metrics.compute(burst)
    assert m.rate_is_reliable is False
    assert "not measurable" in m.as_prompt_block()


def test_realistic_pacing_gives_a_believable_rate() -> None:
    me = uuid.uuid4()
    real = [_seg("I went to the market yesterday with my mother", me, i * 8.0) for i in range(6)]
    m = speech_metrics.compute(real)
    assert m.rate_is_reliable is True
    assert 40 < m.words_per_minute < 150
    assert "words/min of elapsed time" in m.as_prompt_block()


def test_a_single_turn_cannot_give_a_rate() -> None:
    me = uuid.uuid4()
    assert speech_metrics.compute([_seg("I went to the market", me, 0)]).rate_is_reliable is False


# --- whose words (§10.3.0) ------------------------------------------------


def test_each_of_my_turns_is_paired_with_the_line_that_prompted_it() -> None:
    me, partner = uuid.uuid4(), uuid.uuid4()
    segments = [
        _seg("Do you like coffee?", partner, 0),
        _seg("Yes I like it very much", me, 2),
        _seg("Why do you think that is?", partner, 4),
        _seg("Because it helps me wake up", me, 6),
    ]
    turns = build_turns(segments, me)

    assert len(turns) == 2
    assert turns[0].prompt is not None
    assert turns[0].prompt.text == "Do you like coffee?"
    assert turns[1].mine.text == "Because it helps me wake up"


def test_roles_are_labelled_unmistakably_in_the_prompt() -> None:
    me, partner = uuid.uuid4(), uuid.uuid4()
    rendered = render_turns(
        build_turns([_seg("Why?", partner, 0), _seg("Because I like it", me, 1)], me)
    )
    assert "[partner] Why?" in rendered
    assert "[LEARNER] Because I like it" in rendered


def test_incognito_sends_no_partner_context_at_all() -> None:
    """In incognito the whole promise is that nothing about the other person
    persists (PRD §7.2)."""
    me, partner = uuid.uuid4(), uuid.uuid4()
    segments = [_seg("Secret question?", partner, 0), _seg("My answer here", me, 1)]

    turns = build_turns(segments, me, include_partner=False)

    assert turns[0].prompt is None
    assert "Secret question" not in render_turns(turns)


def test_a_quote_the_learner_never_said_is_removed() -> None:
    """Enforced in code: the model has no idea which lines are privacy-sensitive."""
    report = _report(evidence=["I went to Da Nang", "Do you like coffee?"])

    cleaned, removed = strip_foreign_quotes(report, ["I went to Da Nang last weekend"])

    assert removed == 3  # the partner line, in all three criteria
    for criterion in (cleaned.fluency, cleaned.lexical, cleaned.grammar):
        assert criterion.evidence == ["I went to Da Nang"]


def test_quote_matching_ignores_case_and_punctuation() -> None:
    report = _report(evidence=["i went to da nang!"])
    _, removed = strip_foreign_quotes(report, ["I went to Da Nang last weekend."])
    assert removed == 0


# --- the report itself ----------------------------------------------------


def _long_session(me: uuid.UUID) -> list[TranscriptSegment]:
    """Enough words AND enough elapsed time to be measurable.

    The 6-second spacing matters: a session under `MIN_SESSION_SECONDS` reports
    its rate as unmeasurable, which is correct but makes it a poor fixture for
    testing that real numbers reach the model.
    """
    return [
        _seg(
            "I went to Da Nang last weekend with my family and we really enjoyed it",
            me,
            i * 6,
        )
        for i in range(4)
    ]


async def test_a_report_is_built_and_stored() -> None:
    me = uuid.uuid4()
    provider = FakeProvider(parsed=_report((6.0, 6.5, 6.0)))

    async with AsyncSessionLocal() as session:
        service = IeltsService(provider, ROUTE, SessionReportRepository(session))
        report = await service.build_report(me, _long_session(me))
        await session.commit()

    assert Decimal(str(report.band_fluency)) == Decimal("6.0")
    assert Decimal(str(report.band_overall)) == Decimal("6.0")  # mean 6.1666 -> 6.0
    assert Decimal(str(report.next_band)) == Decimal("6.5")
    assert report.summary
    assert len(report.blockers) == 1


async def test_pronunciation_is_never_scored_and_the_overall_says_so() -> None:
    """No model accepts audio. A number here would be invented (§10.3.11)."""
    me = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        service = IeltsService(
            FakeProvider(parsed=_report()), ROUTE, SessionReportRepository(session)
        )
        report = await service.build_report(me, _long_session(me))
        await session.commit()

    assert report.band_pronunciation is None
    assert report.pronunciation_assessed is False
    assert report.overall_is_estimate is True


async def test_the_measured_numbers_reach_the_model() -> None:
    me = uuid.uuid4()
    provider = FakeProvider(parsed=_report())
    async with AsyncSessionLocal() as session:
        service = IeltsService(provider, ROUTE, SessionReportRepository(session))
        await service.build_report(me, _long_session(me))
        await session.commit()

    sent = provider.calls[0].user
    assert "MEASURED" in sent
    assert "words/min of elapsed time" in sent  # 18s session clears the floor
    assert "mean words/turn" in sent
    assert "longest turn" in sent
    # The descriptors must be present, or the model scores from vague memory.
    assert "FLUENCY AND COHERENCE" in provider.calls[0].system


async def test_a_short_session_is_refused_rather_than_banded() -> None:
    """A three-word session would otherwise get a confident, meaningless number."""
    me = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        service = IeltsService(
            FakeProvider(parsed=_report()), ROUTE, SessionReportRepository(session)
        )
        with pytest.raises(NotEnoughSpeech):
            await service.build_report(me, [_seg("yes I agree", me, 0)])


async def test_partner_speech_does_not_count_toward_my_word_floor() -> None:
    me, partner = uuid.uuid4(), uuid.uuid4()
    segments = [_seg("a very long partner monologue " * 10, partner, 0), _seg("Yes", me, 1)]
    async with AsyncSessionLocal() as session:
        service = IeltsService(
            FakeProvider(parsed=_report()), ROUTE, SessionReportRepository(session)
        )
        with pytest.raises(NotEnoughSpeech):
            await service.build_report(me, segments)


async def test_the_stored_report_never_contains_a_partner_quote() -> None:
    me, partner = uuid.uuid4(), uuid.uuid4()
    segments = _long_session(me) + [_seg("What did you do there?", partner, 100)]
    leaky = FakeProvider(parsed=_report(evidence=["What did you do there?"]))

    async with AsyncSessionLocal() as session:
        service = IeltsService(leaky, ROUTE, SessionReportRepository(session))
        report = await service.build_report(me, segments)
        await session.commit()

    assert int(report.quotes_removed) == 3
    assert "What did you do there?" not in str(report.criteria)


async def test_a_provider_failure_does_not_store_an_invented_band() -> None:
    me = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        service = IeltsService(
            FakeProvider(raises=ProviderTimeout("fake")), ROUTE, SessionReportRepository(session)
        )
        with pytest.raises(ReportUnavailable):
            await service.build_report(me, _long_session(me))


async def test_no_structured_output_means_no_report() -> None:
    """A band with nothing behind it is a number we made up."""
    me = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        service = IeltsService(
            FakeProvider(text="Band 7 probably"), ROUTE, SessionReportRepository(session)
        )
        with pytest.raises(ReportUnavailable):
            await service.build_report(me, _long_session(me))


async def test_a_spend_cap_surfaces_as_unavailable() -> None:
    me = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        service = IeltsService(
            FakeProvider(raises=BudgetExceeded("budget", "capped")),
            ROUTE,
            SessionReportRepository(session),
        )
        with pytest.raises(ReportUnavailable):
            await service.build_report(me, _long_session(me))


async def test_a_model_band_outside_the_scale_is_clamped() -> None:
    me = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        service = IeltsService(
            FakeProvider(parsed=_report((99.0, 6.0, 6.0))),
            ROUTE,
            SessionReportRepository(session),
        )
        report = await service.build_report(me, _long_session(me))
        await session.commit()
    assert Decimal(str(report.band_fluency)) == Decimal("9")


async def test_the_mode_is_recorded_so_the_ui_can_be_honest() -> None:
    """A free-conversation band is an estimate; a cue-card band is meaningful."""
    me = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        service = IeltsService(
            FakeProvider(parsed=_report()), ROUTE, SessionReportRepository(session)
        )
        report = await service.build_report(
            me, _long_session(me), mode=ReportMode.ielts_part2
        )
        await session.commit()
    assert report.mode == "ielts_part2"
    assert ReportMode.ielts_part2.is_exam_like
    assert not ReportMode.conversation.is_exam_like


# --- endpoints ------------------------------------------------------------


async def test_report_endpoints_need_authentication(client: AsyncClient) -> None:
    room_id = uuid.uuid4()
    assert (await client.get(f"/api/v1/reports/rooms/{room_id}")).status_code == 401
    assert (await client.get("/api/v1/reports/me/history")).status_code == 401


async def test_no_report_yet_returns_null_not_an_error(client: AsyncClient) -> None:
    auth = (
        await client.post(
            "/api/v1/auth/register",
            json={"username": f"ie{uuid.uuid4().hex[:8]}", "password": "pw12345678"},
        )
    ).json()
    resp = await client.get(
        f"/api/v1/reports/rooms/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {auth['token']}"},
    )
    assert resp.status_code == 200
    assert resp.json() is None


# --- the calibration set itself (docs §10.8) ------------------------------
#
# The band eval costs money and hits the network, so it is a script, not a test.
# What CAN be checked for free is that the gold set stays fit for purpose — a
# set that drifts short or clusters at one band would pass the eval while
# proving nothing.


def _calibration_cases() -> list[dict]:
    import json
    from pathlib import Path

    path = Path(__file__).parent / "data" / "band_calibration.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_the_calibration_set_spans_the_real_band_range() -> None:
    """A set clustered near 6.5 lets a model that answers 6.5 for everything
    score well and be useless (§10.8)."""
    bands = sorted({c["band"] for c in _calibration_cases()})
    assert min(bands) <= 4.5
    assert max(bands) >= 7.5
    assert len(bands) >= 6  # genuinely graded, not two clumps


def test_every_calibration_transcript_clears_the_word_floor() -> None:
    """Below MIN_WORDS_FOR_A_BAND the service refuses to band, so a short case
    would silently drop out of the eval and skew the result."""
    from app.services.ielts import MIN_WORDS_FOR_A_BAND

    for case in _calibration_cases():
        words = sum(
            len(t["text"].split()) for t in case["turns"] if t["who"] == "learner"
        )
        assert words > MIN_WORDS_FOR_A_BAND, f"{case['id']} has only {words} learner words"


def test_calibration_transcripts_carry_realistic_timing() -> None:
    """The `gap` per turn is what makes pauses and rate measurable. Without it
    every case would present identical fluency evidence."""
    for case in _calibration_cases():
        assert all("gap" in turn for turn in case["turns"]), case["id"]
    # Lower bands must actually pause more, or the metrics prove nothing.
    by_band = {c["band"]: c for c in _calibration_cases()}
    low_gaps = statistics.fmean(t["gap"] for t in by_band[4.0]["turns"])
    high_gaps = statistics.fmean(t["gap"] for t in by_band[8.0]["turns"])
    assert low_gaps > high_gaps
