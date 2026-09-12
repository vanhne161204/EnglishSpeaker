"""Shadowing (PRD §8.14): sentences to copy, their model voice, and scoring.

Sentences come from a topic's PUBLISHED doc only — the same trusted content as
Warm-up — so there is nothing extra to author. Every endpoint finds a sentence by
(topic, key) in that list. So an unpublished or deleted sentence can never be
synthesised, scored or assessed, and nobody can make a vendor process text of
their choosing.

Video lessons (Phase 4) work the same way: a sentence is found by (video, key)
among the segments of a PUBLISHED video.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import time
import uuid
import wave
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import ProviderError
from app.ai.metering import UsageSink
from app.ai.pricing import azure_pronunciation_cost, gemini_tts_cost
from app.ai.pronunciation_port import NothingHeard, PronunciationAssessor, PronunciationReport
from app.ai.routing import AiTask
from app.ai.tts_port import Synthesizer
from app.core.config import settings
from app.core.exceptions import AppError, BadRequestError, NotFoundError
from app.models.ai_usage import AiUsage
from app.models.doc import Doc
from app.models.enums import ContentStatus, DocSectionType, PlanTier
from app.models.shadowing import (
    ShadowingAttempt,
    ShadowingClip,
    ShadowingSegment,
    ShadowingVideo,
)
from app.models.topic import Topic
from app.models.user import User
from app.repositories.ai_usage import AiUsageRepository
from app.repositories.doc import DocRepository
from app.repositories.shadowing import ShadowingRepository
from app.schemas.shadowing import (
    PronunciationResult,
    PronunciationWord,
    ShadowingAttemptCreate,
    ShadowingItem,
    ShadowingItemList,
    ShadowingKind,
    ShadowingResult,
    ShadowingSegmentItem,
    ShadowingVideoCard,
    ShadowingVideoLesson,
    WordResult,
)
from app.services.shadowing_score import score_words, tempo

logger = logging.getLogger(__name__)

#: At most this many sentences per topic: a session, not a textbook.
MAX_ITEMS = 40
#: One word is vocabulary, not shadowing; past 25 words nobody can repeat it back.
MIN_WORDS = 2
MAX_WORDS = 25
MAX_CHARS = 300

#: Azure's REST API for short audio takes 30 s at most for pronunciation.
ASSESS_SAMPLE_RATE = 16_000
MIN_ASSESS_SECONDS = 0.3
MAX_ASSESS_SECONDS = 30.0


class ShadowingVoiceUnavailable(AppError):
    """No model voice for this sentence. The browser reads it with its own voice."""

    status_code = 503
    code = "shadowing_voice_unavailable"


class PronunciationUnavailable(AppError):
    status_code = 503
    code = "pronunciation_unavailable"


class PronunciationLimitReached(AppError):
    status_code = 429
    code = "pronunciation_limit"


class PronunciationFailed(AppError):
    status_code = 502
    code = "pronunciation_failed"


class NothingHeardError(AppError):
    status_code = 422
    code = "nothing_heard"


@dataclass(frozen=True, slots=True)
class Sentence:
    key: str
    kind: ShadowingKind
    text: str
    translation: str | None
    audio_url: str | None


def clip_hash(model: str, voice: str, text: str) -> str:
    """Identity of a model-voice clip: same model, voice and text = same audio."""
    return hashlib.sha256(f"{model}\n{voice}\n{text}".encode()).hexdigest()


def collect_sentences(doc: Doc) -> list[Sentence]:
    """The sentences worth shadowing in a doc, in reading order, each only once."""
    found: list[Sentence] = []
    seen: set[str] = set()

    def add(
        kind: ShadowingKind,
        row_id: uuid.UUID,
        text: str | None,
        translation: str | None = None,
        audio_url: str | None = None,
    ) -> None:
        if not text:
            return
        clean = " ".join(text.split())
        if not MIN_WORDS <= len(clean.split()) <= MAX_WORDS or len(clean) > MAX_CHARS:
            return
        folded = clean.casefold().rstrip(".!?")
        if folded in seen:
            return
        seen.add(folded)
        found.append(Sentence(f"{kind}-{row_id}", kind, clean, translation, audio_url))

    for section in doc.sections:
        if section.type == DocSectionType.questions:
            for question in section.questions:
                add(
                    "question",
                    question.id,
                    question.text,
                    question.translation,
                    question.audio_url,
                )
                for answer in question.answer_templates:
                    add("answer", answer.id, answer.example, answer.translation, answer.audio_url)
        elif section.type in (DocSectionType.phrases, DocSectionType.vocabulary):
            for item in section.items:
                if section.type == DocSectionType.phrases:
                    add("term", item.id, item.term, item.translation, item.audio_url)
                add("example", item.id, item.example)
    return found[:MAX_ITEMS]


_NAME_SCAN = re.compile(r"[A-Za-z][A-Za-z'’]*|[.!?]")


def name_tokens(text: str) -> set[str]:
    """Lower-cased words that look like names: capitalised, not starting a sentence,
    and not "I".

    Azure scores every word against English sounds, so a Vietnamese name read
    perfectly still scores badly: in Phase 0 a native-like voice got 61 and 67 on
    "Da Nang". Counting those would punish the learner for the sentence, not
    for their English.
    """
    names: set[str] = set()
    sentence_start = True
    for match in _NAME_SCAN.finditer(text):
        token = match.group(0)
        if token in ".!?":
            sentence_start = True
            continue
        is_i = token == "I" or token.startswith(("I'", "I’"))
        if token[0].isupper() and not sentence_start and not is_i:
            names.add(token.lower())
        sentence_start = False
    return names


def wav_seconds(data: bytes) -> float:
    """Length of a 16 kHz mono 16-bit WAV, or a 400 for anything else."""
    try:
        with wave.open(io.BytesIO(data)) as clip:
            right_format = (
                clip.getnchannels() == 1
                and clip.getsampwidth() == 2
                and clip.getframerate() == ASSESS_SAMPLE_RATE
            )
            frames = clip.getnframes()
    except (wave.Error, EOFError) as exc:
        raise BadRequestError("Send the recording as a WAV file.") from exc
    if not right_format:
        raise BadRequestError("Send 16 kHz, 16-bit, mono WAV audio.")
    seconds = frames / ASSESS_SAMPLE_RATE
    if not MIN_ASSESS_SECONDS <= seconds <= MAX_ASSESS_SECONDS:
        raise BadRequestError("A recording must be between 0.3 and 30 seconds long.")
    return seconds


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def build_pronunciation_result(
    sentence: str, report: PronunciationReport, seconds: float, remaining: int
) -> PronunciationResult:
    """Azure's report, with names taken out of the accuracy score."""
    names = name_tokens(sentence)
    words = [
        PronunciationWord(
            word=word.word,
            accuracy=word.accuracy,
            error=word.error,
            is_name=word.word.lower() in names,
        )
        for word in report.words
    ]
    # Insertions are words the learner added; omissions count as 0 (Azure's own
    # score for a word that was not said).
    scored = [
        word.accuracy or 0.0 for word in words if not word.is_name and word.error != "Insertion"
    ]
    return PronunciationResult(
        accuracy=_mean(scored),
        fluency=report.fluency,
        completeness=report.completeness,
        prosody=report.prosody,
        words=words,
        heard=report.recognized,
        seconds=round(seconds, 2),
        remaining_today=remaining,
    )


def _find(sentences: list[Sentence], key: str) -> Sentence:
    for sentence in sentences:
        if sentence.key == key:
            return sentence
    raise NotFoundError("Sentence not found in this lesson")


def segment_key(segment_id: uuid.UUID) -> str:
    """The item key of a video sentence."""
    return f"segment-{segment_id}"


def _segment_sentence(segment: ShadowingSegment) -> Sentence:
    return Sentence(segment_key(segment.id), "segment", segment.text, segment.translation, None)


def _ms_since(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _day_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class ShadowingService:
    def __init__(
        self,
        session: AsyncSession,
        synthesizer: Synthesizer | None,
        assessor: PronunciationAssessor | None = None,
        sink: UsageSink | None = None,
    ) -> None:
        self.session = session
        self.docs = DocRepository(session)
        self.repo = ShadowingRepository(session)
        self.synthesizer = synthesizer
        self.assessor = assessor
        self.sink = sink or UsageSink()

    async def items(self, user: User, topic_id: uuid.UUID) -> ShadowingItemList:
        topic, level, sentences = await self._sentences(topic_id)
        best = await self.repo.best_scores(user.id, topic.id)
        return ShadowingItemList(
            topic_id=topic.id,
            topic_title=topic.title,
            level=level,
            voice_enabled=self.synthesizer is not None,
            assess_enabled=self.assessor is not None,
            assess_remaining=await self._checks_left(user) if self.assessor else 0,
            items=[
                ShadowingItem(
                    key=sentence.key,
                    kind=sentence.kind,
                    text=sentence.text,
                    translation=sentence.translation,
                    audio_url=sentence.audio_url,
                    best_score=best[sentence.key][0] if sentence.key in best else None,
                    attempts=best[sentence.key][1] if sentence.key in best else 0,
                )
                for sentence in sentences
            ],
        )

    async def clip(self, topic_id: uuid.UUID, key: str) -> ShadowingClip:
        """The model voice for one sentence: from the table, or made now and kept."""
        _, _, sentences = await self._sentences(topic_id)
        sentence = _find(sentences, key)
        synthesizer = self.synthesizer
        if synthesizer is None:
            raise ShadowingVoiceUnavailable(
                "Model voices are not switched on. Your browser's voice is used instead."
            )

        text_hash = clip_hash(synthesizer.model, synthesizer.voice, sentence.text)
        cached = await self.repo.clip_by_hash(text_hash)
        if cached is not None:
            return cached
        await self._check_org_budget(ShadowingVoiceUnavailable)

        started = time.perf_counter()
        try:
            made = await synthesizer.synthesize(sentence.text)
        except ProviderError as exc:
            logger.warning("Shadowing TTS failed: %s", exc)
            await self.sink.record(
                AiUsage(
                    task=AiTask.shadowing_tts.value,
                    provider=exc.provider,
                    model=synthesizer.model,
                    latency_ms=_ms_since(started),
                    ok=False,
                )
            )
            raise ShadowingVoiceUnavailable(
                "The model voice could not be made right now. Your browser's voice is used instead."
            ) from exc

        # On its own session: the money is spent even if saving the clip fails.
        # No user id — the clip is shared content, made once for everyone.
        await self.sink.record(
            AiUsage(
                task=AiTask.shadowing_tts.value,
                provider=made.provider,
                model=made.model,
                input_tokens=made.input_tokens,
                output_tokens=made.output_tokens,
                cost_usd=gemini_tts_cost(
                    made.model, made.input_tokens, made.output_tokens, made.duration_ms
                ),
                latency_ms=_ms_since(started),
                ok=True,
            )
        )

        row = ShadowingClip(
            text_hash=text_hash,
            text=sentence.text,
            provider=made.provider,
            model=made.model,
            voice=made.voice,
            mime_type="audio/wav",
            duration_ms=made.duration_ms,
            data=made.wav,
        )
        try:
            async with self.session.begin_nested():
                await self.repo.add_clip(row)
        except IntegrityError:
            # Another request made the same clip a moment ago. Serve that one.
            existing = await self.repo.clip_by_hash(text_hash)
            if existing is None:
                raise
            return existing
        return row

    async def record_attempt(
        self, user: User, payload: ShadowingAttemptCreate
    ) -> ShadowingResult:
        sentences = await self._sentences_for(payload.topic_id, payload.video_id)
        sentence = _find(sentences, payload.item_key)
        heard = " ".join(payload.heard_text.split())
        match = score_words(sentence.text, heard)
        ratio, pace = tempo(payload.duration_ms, payload.reference_ms)

        await self.repo.add_attempt(
            ShadowingAttempt(
                user_id=user.id,
                topic_id=payload.topic_id,
                video_id=payload.video_id,
                item_key=sentence.key,
                reference_text=sentence.text,
                heard_text=heard,
                score=match.score,
                words_total=len(match.words),
                words_ok=match.words_ok,
                duration_ms=payload.duration_ms,
                reference_ms=payload.reference_ms,
                engine=payload.engine,
            )
        )
        scores = await self.repo.best_scores(user.id, payload.topic_id, video_id=payload.video_id)
        best, attempts = scores[sentence.key]
        return ShadowingResult(
            score=match.score,
            words=[
                WordResult(word=word.word, heard=word.heard, status=word.status, hint=word.hint)
                for word in match.words
            ],
            extra=match.extra,
            tempo_ratio=ratio,
            tempo=pace,
            best_score=best,
            attempts=attempts,
        )

    async def assess(
        self,
        user: User,
        topic_id: uuid.UUID | None,
        key: str,
        audio: bytes,
        video_id: uuid.UUID | None = None,
    ) -> PronunciationResult:
        """Phase 2: a real pronunciation check of one try, by Azure.

        The audio is passed straight through and never stored. Every check is
        metered in ai_usage at the list price (task "pronunciation").
        """
        assessor = self.assessor
        if assessor is None:
            raise PronunciationUnavailable("Pronunciation checks are not switched on.")
        sentence = _find(await self._sentences_for(topic_id, video_id), key)
        seconds = wav_seconds(audio)

        remaining = await self._checks_left(user)
        if remaining <= 0:
            raise PronunciationLimitReached(
                f"You have used today's {self._daily_checks(user)} pronunciation checks. "
                "They come back at 00:00 UTC (07:00 in Vietnam)."
            )
        await self._check_org_budget(PronunciationUnavailable)

        started = time.perf_counter()
        cost = azure_pronunciation_cost(seconds, assessor.prosody)
        try:
            report = await assessor.assess(audio, sentence.text)
        except NothingHeard as exc:
            # Azure listened to the whole clip, so it is billed and counts.
            await self._record_check(user, assessor.model, seconds, cost, started, ok=True)
            raise NothingHeardError(
                "No speech was heard in that recording. Try again, closer to the mic."
            ) from exc
        except ProviderError as exc:
            logger.warning("Pronunciation check failed: %s", exc)
            # ok=False: shows as an outage in the admin panel, and does not use up
            # the learner's check.
            await self._record_check(
                user, assessor.model, seconds, Decimal(0), started, ok=False, provider=exc.provider
            )
            raise PronunciationFailed(
                "The pronunciation check failed. Please try again in a moment."
            ) from exc

        await self._record_check(
            user, report.model, seconds, cost, started, ok=True, words=len(report.words)
        )
        return build_pronunciation_result(sentence.text, report, seconds, remaining - 1)

    # --- video lessons (Phase 4) ---------------------------------------------

    async def videos(self, user: User) -> list[ShadowingVideoCard]:
        """Published video lessons, newest first, with how far this learner got."""
        practised = await self.repo.practised_by_video(user.id)
        return [
            ShadowingVideoCard(
                id=video.id,
                youtube_id=video.youtube_id,
                title=video.title,
                level=video.level,
                sentences=len(video.segments),
                practised=practised.get(video.id, 0),
            )
            for video in await self.repo.list_videos(published_only=True)
            if video.segments
        ]

    async def video_items(self, user: User, video_id: uuid.UUID) -> ShadowingVideoLesson:
        video = await self._published_video(video_id)
        best = await self.repo.best_scores(user.id, video_id=video.id)
        items: list[ShadowingSegmentItem] = []
        for segment in video.segments:
            key = segment_key(segment.id)
            items.append(
                ShadowingSegmentItem(
                    key=key,
                    text=segment.text,
                    translation=segment.translation,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    best_score=best[key][0] if key in best else None,
                    attempts=best[key][1] if key in best else 0,
                )
            )
        return ShadowingVideoLesson(
            id=video.id,
            youtube_id=video.youtube_id,
            title=video.title,
            level=video.level,
            source_note=video.source_note,
            assess_enabled=self.assessor is not None,
            assess_remaining=await self._checks_left(user) if self.assessor else 0,
            items=items,
        )

    # --- internals ---------------------------------------------------------

    async def _sentences(self, topic_id: uuid.UUID) -> tuple[Topic, str | None, list[Sentence]]:
        topic = await self.session.get(Topic, topic_id)
        if topic is None or topic.status != ContentStatus.published:
            raise NotFoundError("Topic not found")
        doc = await self.docs.get_by_topic(topic_id)
        if doc is None or doc.status != ContentStatus.published:
            return topic, topic.level, []
        return topic, doc.level or topic.level, collect_sentences(doc)

    async def _sentences_for(
        self, topic_id: uuid.UUID | None, video_id: uuid.UUID | None
    ) -> list[Sentence]:
        """The sentences of a topic or of a video lesson: exactly one is given."""
        if topic_id is not None and video_id is not None:
            raise BadRequestError("Give either topic_id or video_id, not both.")
        if video_id is not None:
            video = await self._published_video(video_id)
            return [_segment_sentence(segment) for segment in video.segments]
        if topic_id is None:
            raise BadRequestError("Give either topic_id or video_id.")
        _, _, sentences = await self._sentences(topic_id)
        return sentences

    async def _published_video(self, video_id: uuid.UUID) -> ShadowingVideo:
        video = await self.repo.get_video(video_id)
        if video is None or video.status != ContentStatus.published:
            raise NotFoundError("Video not found")
        return video

    def _daily_checks(self, user: User) -> int:
        if user.plan == PlanTier.premium:
            return settings.pronunciation_premium_daily
        return settings.pronunciation_free_daily

    async def _checks_left(self, user: User) -> int:
        used = await AiUsageRepository(self.session).call_count_since(
            _day_start(), user.id, AiTask.pronunciation.value, ok_only=True
        )
        return max(self._daily_checks(user) - used, 0)

    async def _record_check(
        self,
        user: User,
        model: str,
        seconds: float,
        cost: Decimal,
        started: float,
        *,
        ok: bool,
        provider: str = "azure",
        words: int = 0,
    ) -> None:
        # On its own session, so it survives this request failing afterwards.
        await self.sink.record(
            AiUsage(
                user_id=user.id,
                task=AiTask.pronunciation.value,
                provider=provider,
                model=model,
                # Whole seconds of audio: the billing unit, as for Deepgram.
                input_tokens=round(seconds),
                output_tokens=words,
                cost_usd=cost,
                latency_ms=_ms_since(started),
                ok=ok,
            )
        )

    async def _check_org_budget(self, error: type[AppError]) -> None:
        ceiling = Decimal(str(settings.ai_monthly_budget_usd))
        if ceiling <= 0:
            return
        spent = await AiUsageRepository(self.session).spend_since(
            datetime.now(UTC) - timedelta(days=30)
        )
        if spent >= ceiling:
            logger.error(
                "AI monthly budget exhausted: $%s of $%s — shadowing refused", spent, ceiling
            )
            raise error("AI features are paused for now. Please try again later.")
