"""Shadowing (PRD §8.14): sentences, model voices, and word-match scoring.

Offline: a ``FakeSynthesizer`` stands in for Gemini TTS, so these assert our own
rules — which sentences are offered, that a clip is made once, what is scored —
not Google's behaviour.
"""

from __future__ import annotations

import io
import uuid
import wave
from collections.abc import Iterator
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.ai.pricing import gemini_tts_cost
from app.ai.providers.gemini_tts import pcm_to_wav
from app.ai.tts_port import SpeechClip
from app.api.deps import get_synthesizer
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.ai_usage import AiUsage
from app.models.doc import AnswerTemplate, Doc, DocItem, DocSection, Question
from app.models.shadowing import ShadowingClip
from app.models.topic import Topic
from app.services.shadowing_score import score_words, tempo

BASE = "/api/v1/shadowing"
QUESTION = "Where did you go last summer?"


class FakeSynthesizer:
    name = "gemini"
    model = "gemini-3.1-flash-tts-preview"
    voice = "Kore"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def synthesize(self, text: str) -> SpeechClip:
        self.calls.append(text)
        pcm = b"\x00\x00" * 24_000  # one second of silence
        return SpeechClip(
            wav=pcm_to_wav(pcm, 24_000),
            duration_ms=1000,
            provider="gemini",
            model=self.model,
            voice=self.voice,
            input_tokens=20,
            output_tokens=25,
        )


@pytest.fixture
def synth() -> Iterator[FakeSynthesizer]:
    fake = FakeSynthesizer()
    app.dependency_overrides[get_synthesizer] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_synthesizer, None)


@pytest.fixture(autouse=True)
def budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", 50.0)


def _audio_url(topic_id: uuid.UUID, key: str) -> str:
    return f"{BASE}/topics/{topic_id}/items/{key}/audio"


async def _make_topic(
    *, slug: str = "travel", doc_status: str = "published", question: str = QUESTION
) -> dict[str, uuid.UUID]:
    """A topic whose doc has one question (with an answer) and two phrases."""
    async with AsyncSessionLocal() as session:
        topic = Topic(slug=slug, title=slug.title(), level="A2")
        session.add(topic)
        await session.flush()
        doc = Doc(topic_id=topic.id, status=doc_status)
        session.add(doc)
        await session.flush()
        questions = DocSection(doc_id=doc.id, type="questions", sort_order=0)
        phrases = DocSection(doc_id=doc.id, type="phrases", sort_order=1)
        session.add_all([questions, phrases])
        await session.flush()
        q = Question(section_id=questions.id, text=question, translation="Hè năm ngoái bạn đi đâu?")
        session.add(q)
        await session.flush()
        answer = AnswerTemplate(
            question_id=q.id, template="I went to ___.", example="I went to Da Nang with my family."
        )
        single_word = DocItem(section_id=phrases.id, term="Hello", sort_order=0)
        phrase = DocItem(
            section_id=phrases.id,
            term="Could you say that again?",
            example="Sorry, could you say that again?",
            sort_order=1,
        )
        session.add_all([answer, single_word, phrase])
        await session.commit()
        return {"topic": topic.id, "question": q.id, "answer": answer.id, "phrase": phrase.id}


# --- the sentence list ------------------------------------------------------


async def test_items_require_sign_in(client: AsyncClient) -> None:
    ids = await _make_topic()
    resp = await client.get(f"{BASE}/topics/{ids['topic']}/items")
    assert resp.status_code == 401


async def test_items_come_from_the_published_doc(user_client: AsyncClient) -> None:
    ids = await _make_topic()
    resp = await user_client.get(f"{BASE}/topics/{ids['topic']}/items")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Reading order; the one-word phrase is not a sentence to shadow.
    assert [item["key"] for item in body["items"]] == [
        f"question-{ids['question']}",
        f"answer-{ids['answer']}",
        f"term-{ids['phrase']}",
        f"example-{ids['phrase']}",
    ]
    first = body["items"][0]
    assert first["text"] == QUESTION
    assert first["translation"] == "Hè năm ngoái bạn đi đâu?"
    assert first["best_score"] is None and first["attempts"] == 0
    # conftest forces AI_ENABLED=false, so there is no TTS: browser voice.
    assert body["voice_enabled"] is False


async def test_a_draft_doc_offers_nothing(user_client: AsyncClient) -> None:
    ids = await _make_topic(doc_status="draft")
    body = (await user_client.get(f"{BASE}/topics/{ids['topic']}/items")).json()
    assert body["items"] == []


async def test_unknown_topic_is_404(user_client: AsyncClient) -> None:
    resp = await user_client.get(f"{BASE}/topics/{uuid.uuid4()}/items")
    assert resp.status_code == 404


# --- model voices -----------------------------------------------------------


async def test_no_tts_means_browser_voice(user_client: AsyncClient) -> None:
    ids = await _make_topic()
    resp = await user_client.get(_audio_url(ids["topic"], f"question-{ids['question']}"))
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "shadowing_voice_unavailable"


async def test_a_clip_is_made_once_then_served_from_the_table(
    user_client: AsyncClient, synth: FakeSynthesizer
) -> None:
    ids = await _make_topic()
    url = _audio_url(ids["topic"], f"question-{ids['question']}")

    first = await user_client.get(url)
    assert first.status_code == 200, first.text
    assert first.headers["content-type"] == "audio/wav"
    assert first.content.startswith(b"RIFF")
    etag = first.headers["etag"]

    second = await user_client.get(url)
    assert second.status_code == 200
    assert synth.calls == [QUESTION]  # made once, not per play

    unchanged = await user_client.get(url, headers={"If-None-Match": etag})
    assert unchanged.status_code == 304

    async with AsyncSessionLocal() as session:
        stmt = select(AiUsage).where(AiUsage.task == "shadowing_tts")
        rows = list((await session.execute(stmt)).scalars())
    assert len(rows) == 1 and rows[0].ok
    assert Decimal(str(rows[0].cost_usd)) == gemini_tts_cost(synth.model, 20, 25, 1000)


async def test_the_same_sentence_in_two_topics_shares_one_clip(
    user_client: AsyncClient, synth: FakeSynthesizer
) -> None:
    a = await _make_topic(slug="travel")
    b = await _make_topic(slug="holidays")
    for ids in (a, b):
        resp = await user_client.get(_audio_url(ids["topic"], f"question-{ids['question']}"))
        assert resp.status_code == 200
    assert synth.calls == [QUESTION]
    async with AsyncSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(ShadowingClip))
    assert count == 1


async def test_tts_only_reads_sentences_of_that_topic(
    user_client: AsyncClient, synth: FakeSynthesizer
) -> None:
    a = await _make_topic(slug="travel")
    b = await _make_topic(slug="food", question="What did you eat for breakfast?")
    # B's sentence through A's topic, and a made-up key: both refused.
    cross = await user_client.get(_audio_url(a["topic"], f"question-{b['question']}"))
    made_up = await user_client.get(_audio_url(a["topic"], f"question-{uuid.uuid4()}"))
    assert cross.status_code == 404
    assert made_up.status_code == 404
    assert synth.calls == []


async def test_spent_budget_falls_back_to_the_browser_voice(
    user_client: AsyncClient, synth: FakeSynthesizer
) -> None:
    ids = await _make_topic()
    async with AsyncSessionLocal() as session:
        session.add(
            AiUsage(task="rescue", provider="openai", model="gpt-4o-mini", cost_usd=Decimal("60"))
        )
        await session.commit()
    resp = await user_client.get(_audio_url(ids["topic"], f"question-{ids['question']}"))
    assert resp.status_code == 503
    assert synth.calls == []


# --- scoring a try ----------------------------------------------------------


async def test_an_attempt_is_scored_and_kept_as_the_best(user_client: AsyncClient) -> None:
    ids = await _make_topic()
    key = f"question-{ids['question']}"
    payload = {
        "topic_id": str(ids["topic"]),
        "item_key": key,
        "heard_text": "where you go last summer",
        "duration_ms": 2100,
        "reference_ms": 1900,
        "engine": "browser",
    }

    resp = await user_client.post(f"{BASE}/attempts", json=payload)
    assert resp.status_code == 201, resp.text
    result = resp.json()
    assert result["score"] == 83  # 5 of 6 words
    missed = [word["word"] for word in result["words"] if word["status"] == "missed"]
    assert missed == ["did"]
    assert result["tempo"] == "good"
    assert result["best_score"] == 83 and result["attempts"] == 1

    better = await user_client.post(
        f"{BASE}/attempts", json={**payload, "heard_text": "where did you go last summer"}
    )
    assert better.json()["score"] == 100
    assert better.json()["best_score"] == 100 and better.json()["attempts"] == 2

    items = (await user_client.get(f"{BASE}/topics/{ids['topic']}/items")).json()["items"]
    assert items[0]["best_score"] == 100 and items[0]["attempts"] == 2


async def test_attempts_need_a_real_sentence_and_a_user(
    client: AsyncClient, user_client: AsyncClient
) -> None:
    ids = await _make_topic()
    bad_key = {"topic_id": str(ids["topic"]), "item_key": "question-nope", "heard_text": "hi"}
    assert (await user_client.post(f"{BASE}/attempts", json=bad_key)).status_code == 404

    user_client.headers.pop("Authorization")
    anonymous = {**bad_key, "item_key": f"question-{ids['question']}"}
    assert (await client.post(f"{BASE}/attempts", json=anonymous)).status_code == 401


# --- the word matcher -------------------------------------------------------


def test_contractions_and_numbers_are_the_same_words() -> None:
    assert score_words("I'm fine, thanks.", "i am fine thanks").score == 100
    assert score_words("I am fine.", "I'm fine").score == 100
    assert score_words("I have 2 cats.", "i have two cats").score == 100


def test_near_spellings_count_half() -> None:
    result = score_words("My favourite colour is blue.", "my favorite color is blue")
    statuses = {word.word: word.status for word in result.words}
    assert statuses["favourite"] == "close" and statuses["colour"] == "close"
    assert result.score == 80  # (3 + 0.5 + 0.5) / 5


def test_extra_words_are_listed_but_not_punished() -> None:
    result = score_words("Good morning.", "good morning everyone")
    assert result.score == 100
    assert result.extra == ["everyone"]


def test_silence_scores_zero() -> None:
    result = score_words("See you tomorrow.", "")
    assert result.score == 0
    assert {word.status for word in result.words} == {"missed"}


def test_a_half_said_contraction_is_wrong_not_missed() -> None:
    result = score_words("I'm ready.", "i ready")
    assert result.words[0].word == "I'm"
    assert result.words[0].status == "wrong"


def test_tempo_labels() -> None:
    assert tempo(2600, 2000) == (1.3, "good")
    assert tempo(3000, 2000) == (1.5, "slow")
    assert tempo(1000, 2000) == (0.5, "fast")
    assert tempo(None, 2000) == (None, None)


# --- audio and pricing helpers ----------------------------------------------


def test_pcm_is_wrapped_in_a_playable_wav() -> None:
    wav = pcm_to_wav(b"\x00\x00" * 24_000, 24_000)
    with wave.open(io.BytesIO(wav)) as read:
        assert read.getframerate() == 24_000
        assert read.getnframes() == 24_000
        assert read.getnchannels() == 1


def test_tts_cost_uses_reported_tokens_or_the_clip_length() -> None:
    model = "gemini-3.1-flash-tts-preview"
    # 20 text tokens at $1/M + 100 audio tokens at $20/M.
    assert gemini_tts_cost(model, 20, 100, 4000) == Decimal("0.00202")
    # No usage reported: 4 s x 25 tokens/s = 100 audio tokens.
    assert gemini_tts_cost(model, 0, 0, 4000) == Decimal("0.002")
