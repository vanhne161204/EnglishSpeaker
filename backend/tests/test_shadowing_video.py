"""Shadowing Phase 4 (PRD §8.14): YouTube video lessons.

Admins add a video, type its sentences and mark their times; learners shadow
them one sentence at a time. The video itself never reaches the server, so these
tests are about our own rules: who may do what, what gets published, and that
learners' scores survive an admin's edits.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.ai.pronunciation_port import AssessedWord, PronunciationReport
from app.ai.providers.gemini_tts import pcm_to_wav
from app.api.deps import get_assessor
from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.shadowing import ShadowingAttempt
from app.services.shadowing_score import ending_hint, score_words
from app.services.shadowing_video import parse_youtube_id

ADMIN = "/api/v1/admin/shadowing/videos"
BASE = "/api/v1/shadowing"
YOUTUBE_ID = "dQw4w9WgXcQ"
SENTENCES = [
    (1000, 2500, "Can I get a latte, please?"),
    (3000, 4800, "I worked there for two years."),
]


class FakeAssessor:
    name = "azure"
    model = "pronunciation-assessment"
    prosody = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def assess(self, wav_16k_mono: bytes, reference_text: str) -> PronunciationReport:
        self.calls.append(reference_text)
        return PronunciationReport(
            accuracy=90.0,
            fluency=90.0,
            completeness=100.0,
            prosody=80.0,
            overall=88.0,
            recognized=reference_text,
            words=[
                AssessedWord(word.strip(".,?"), 90.0, "None") for word in reference_text.split()
            ],
            provider="azure",
            model=self.model,
        )


@pytest.fixture(autouse=True)
def limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pronunciation_free_daily", 3)
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", 50.0)


@pytest.fixture
def assessor() -> Iterator[FakeAssessor]:
    fake = FakeAssessor()
    app.dependency_overrides[get_assessor] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_assessor, None)


def _segments(rows: list[tuple[int, int, str]]) -> dict[str, Any]:
    return {"segments": [{"start_ms": s, "end_ms": e, "text": t} for s, e, t in rows]}


async def _make_video(
    admin: AsyncClient, *, publish: bool = True, source_note: str = "Our own channel"
) -> dict[str, Any]:
    created = await admin.post(
        ADMIN,
        json={
            "youtube": f"https://youtu.be/{YOUTUBE_ID}",
            "title": "Ordering coffee",
            "level": "beginner",
            "source_note": source_note,
        },
    )
    assert created.status_code == 201, created.text
    video_id = created.json()["id"]
    saved = await admin.put(f"{ADMIN}/{video_id}/segments", json=_segments(SENTENCES))
    assert saved.status_code == 200, saved.text
    if not publish:
        return saved.json()
    published = await admin.patch(f"{ADMIN}/{video_id}", json={"status": "published"})
    assert published.status_code == 200, published.text
    return published.json()


async def _lesson(learner: AsyncClient, video_id: str) -> dict[str, Any]:
    resp = await learner.get(f"{BASE}/videos/{video_id}/items")
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- YouTube links -------------------------------------------------------------


@pytest.mark.parametrize(
    "link",
    [
        YOUTUBE_ID,
        f"https://www.youtube.com/watch?v={YOUTUBE_ID}&t=42s",
        f"youtu.be/{YOUTUBE_ID}",
        f"https://youtu.be/{YOUTUBE_ID}?si=abc",
        f"https://m.youtube.com/watch?v={YOUTUBE_ID}",
        f"https://www.youtube.com/shorts/{YOUTUBE_ID}",
        f"https://www.youtube.com/embed/{YOUTUBE_ID}",
        f"https://www.youtube-nocookie.com/embed/{YOUTUBE_ID}",
    ],
)
def test_youtube_links_are_read(link: str) -> None:
    assert parse_youtube_id(link) == YOUTUBE_ID


@pytest.mark.parametrize(
    "link",
    [
        "https://vimeo.com/123456789",
        "https://www.youtube.com/watch?v=short",
        f"https://evil.example/watch?v={YOUTUBE_ID}",
        "not a link at all",
    ],
)
def test_other_links_are_refused(link: str) -> None:
    with pytest.raises(BadRequestError):
        parse_youtube_id(link)


# --- admin -----------------------------------------------------------------------


async def test_an_admin_builds_and_publishes_a_video(admin_client: AsyncClient) -> None:
    created = await admin_client.post(
        ADMIN,
        json={
            "youtube": f"https://www.youtube.com/watch?v={YOUTUBE_ID}",
            "title": "Ordering coffee",
            "source_note": "Creative Commons BY",
        },
    )
    assert created.status_code == 201, created.text
    video = created.json()
    assert video["youtube_id"] == YOUTUBE_ID
    assert video["status"] == "draft" and video["sentences"] == 0

    # Nothing to shadow yet, so it cannot be published.
    early = await admin_client.patch(f"{ADMIN}/{video['id']}", json={"status": "published"})
    assert early.status_code == 400
    assert early.json()["error"]["code"] == "video_not_ready"

    # Sent out of order, stored in time order.
    saved = await admin_client.put(
        f"{ADMIN}/{video['id']}/segments", json=_segments(list(reversed(SENTENCES)))
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert [s["text"] for s in body["segments"]] == [text for _, _, text in SENTENCES]
    assert [s["position"] for s in body["segments"]] == [0, 1]

    published = await admin_client.patch(f"{ADMIN}/{video['id']}", json={"status": "published"})
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    listed = (await admin_client.get(ADMIN)).json()
    assert [(v["title"], v["sentences"]) for v in listed] == [("Ordering coffee", 2)]

    actions = {entry["action"] for entry in (await admin_client.get("/api/v1/admin/audit")).json()}
    assert {"video.create", "video.sentences", "video.update"} <= actions


async def test_publishing_needs_a_source_note(admin_client: AsyncClient) -> None:
    video = await _make_video(admin_client, publish=False, source_note="")
    resp = await admin_client.patch(f"{ADMIN}/{video['id']}", json={"status": "published"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "video_not_ready"


@pytest.mark.parametrize(
    ("row", "problem"),
    [
        ((1000, 1200, "Too short."), "0.3 s"),
        ((1000, 32_000, "Far too long for one breath."), "30 seconds"),
        ((1000, 3000, " ".join(["word"] * 41)), "1 to 40 words"),
        ((1000, 3000, "   "), "1 to 40 words"),
    ],
)
async def test_bad_sentences_are_refused(
    admin_client: AsyncClient, row: tuple[int, int, str], problem: str
) -> None:
    video = await _make_video(admin_client, publish=False)
    resp = await admin_client.put(f"{ADMIN}/{video['id']}/segments", json=_segments([row]))
    assert resp.status_code == 400
    message = resp.json()["error"]["message"]
    assert message.startswith("Sentence 1:") and problem in message


async def test_a_published_video_keeps_at_least_one_sentence(admin_client: AsyncClient) -> None:
    video = await _make_video(admin_client)
    resp = await admin_client.put(f"{ADMIN}/{video['id']}/segments", json={"segments": []})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "video_not_ready"


async def test_only_admins_manage_videos(user_client: AsyncClient) -> None:
    assert (await user_client.get(ADMIN)).status_code == 403
    resp = await user_client.post(ADMIN, json={"youtube": YOUTUBE_ID, "title": "Mine"})
    assert resp.status_code == 403


# --- learners --------------------------------------------------------------------


async def test_learners_see_only_published_videos(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    draft = await _make_video(admin_client, publish=False)
    assert (await other_client.get(f"{BASE}/videos")).json() == []
    assert (await other_client.get(f"{BASE}/videos/{draft['id']}/items")).status_code == 404

    await admin_client.patch(f"{ADMIN}/{draft['id']}", json={"status": "published"})
    cards = (await other_client.get(f"{BASE}/videos")).json()
    assert [(c["youtube_id"], c["sentences"], c["practised"]) for c in cards] == [
        (YOUTUBE_ID, 2, 0)
    ]
    lesson = await _lesson(other_client, draft["id"])
    assert lesson["source_note"] == "Our own channel"
    assert [(i["start_ms"], i["end_ms"]) for i in lesson["items"]] == [(1000, 2500), (3000, 4800)]
    assert all(i["key"].startswith("segment-") for i in lesson["items"])


async def test_a_try_at_a_video_sentence(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    video = await _make_video(admin_client)
    item = (await _lesson(other_client, video["id"]))["items"][1]

    resp = await other_client.post(
        f"{BASE}/attempts",
        json={
            "video_id": video["id"],
            "item_key": item["key"],
            "heard_text": "I work there for two years",
            "duration_ms": 1700,
            "reference_ms": item["end_ms"] - item["start_ms"],
        },
    )
    assert resp.status_code == 201, resp.text
    result = resp.json()
    worked = next(w for w in result["words"] if w["word"] == "worked")
    assert worked["status"] == "close" and worked["hint"] == "-ed"
    assert result["score"] == 92  # five words right, "worked" half right: 5.5 / 6
    assert result["tempo"] == "good"

    cards = (await other_client.get(f"{BASE}/videos")).json()
    assert cards[0]["practised"] == 1
    assert (await _lesson(other_client, video["id"]))["items"][1]["best_score"] == 92


@pytest.mark.parametrize("sources", [{}, {"topic_id": True, "video_id": True}])
async def test_a_try_names_exactly_one_source(
    admin_client: AsyncClient, other_client: AsyncClient, sources: dict[str, bool]
) -> None:
    video = await _make_video(admin_client)
    body: dict[str, Any] = {"item_key": "segment-x", "heard_text": "hello"}
    if sources:
        body |= {"topic_id": video["id"], "video_id": video["id"]}
    resp = await other_client.post(f"{BASE}/attempts", json=body)
    assert resp.status_code == 422


async def test_scores_survive_an_admin_edit(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    video = await _make_video(admin_client)
    first, second = (await _lesson(other_client, video["id"]))["items"]
    await other_client.post(
        f"{BASE}/attempts",
        json={"video_id": video["id"], "item_key": second["key"], "heard_text": second["text"]},
    )

    # The admin fixes a time, keeps both sentences by id, and adds a third.
    detail = (await admin_client.get(f"{ADMIN}/{video['id']}")).json()
    rows = [{**s, "start_ms": s["start_ms"] + 100} for s in detail["segments"]]
    rows.append({"start_ms": 6000, "end_ms": 7000, "text": "Thanks a lot."})
    saved = await admin_client.put(f"{ADMIN}/{video['id']}/segments", json={"segments": rows})
    assert saved.status_code == 200, saved.text

    items = (await _lesson(other_client, video["id"]))["items"]
    assert [i["key"] for i in items[:2]] == [first["key"], second["key"]]
    assert items[1]["best_score"] == 100 and items[0]["start_ms"] == 1100
    assert items[2]["best_score"] is None

    # Leaving a sentence out deletes it.
    second_id = second["key"].removeprefix("segment-")
    kept = [s for s in saved.json()["segments"] if s["id"] != second_id]
    await admin_client.put(f"{ADMIN}/{video['id']}/segments", json={"segments": kept})
    keys = [i["key"] for i in (await _lesson(other_client, video["id"]))["items"]]
    assert second["key"] not in keys and len(keys) == 2


async def test_a_pronunciation_check_on_a_video_sentence(
    admin_client: AsyncClient, other_client: AsyncClient, assessor: FakeAssessor
) -> None:
    video = await _make_video(admin_client)
    lesson = await _lesson(other_client, video["id"])
    assert lesson["assess_enabled"] is True and lesson["assess_remaining"] == 3

    wav = pcm_to_wav(b"\x00\x00" * 16_000 * 2, 16_000)
    resp = await other_client.post(
        f"{BASE}/assess",
        data={"video_id": video["id"], "item_key": lesson["items"][0]["key"]},
        files={"audio": ("take.wav", wav, "audio/wav")},
    )
    assert resp.status_code == 200, resp.text
    assert assessor.calls == ["Can I get a latte, please?"]
    assert resp.json()["remaining_today"] == 2


async def test_deleting_a_video_deletes_its_tries(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    video = await _make_video(admin_client)
    item = (await _lesson(other_client, video["id"]))["items"][0]
    await other_client.post(
        f"{BASE}/attempts",
        json={"video_id": video["id"], "item_key": item["key"], "heard_text": item["text"]},
    )

    assert (await admin_client.delete(f"{ADMIN}/{video['id']}")).status_code == 204
    assert (await other_client.get(f"{BASE}/videos/{video['id']}/items")).status_code == 404
    async with AsyncSessionLocal() as session:
        left = await session.scalar(select(func.count()).select_from(ShadowingAttempt))
    assert left == 0


# --- word-ending hints -------------------------------------------------------------


@pytest.mark.parametrize(
    ("expected", "heard", "hint"),
    [
        ("worked", "work", "-ed"),
        ("liked", "like", "-ed"),
        ("stopped", "stop", "-ed"),
        ("studied", "study", "-ed"),
        ("cats", "cat", "-s"),
        ("watches", "watch", "-s"),
        ("studies", "study", "-s"),
        ("making", "make", "-ing"),
        ("running", "run", "-ing"),
        ("Tom's", "tom", "-'s"),
        ("his", "hi", None),  # a different word, not a dropped ending
        ("work", "worked", None),  # an ending added is not an ending dropped
        ("worked", "walked", None),
        ("worked", None, None),
    ],
)
def test_ending_hints(expected: str, heard: str | None, hint: str | None) -> None:
    assert ending_hint(expected, heard) == hint


def test_hints_come_with_the_word_match() -> None:
    words = {w.word: w for w in score_words("Two cats worked here.", "two cat work here").words}
    assert words["cats"].hint == "-s"
    assert words["worked"].hint == "-ed"
    assert words["here"].hint is None
