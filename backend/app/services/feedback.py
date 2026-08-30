"""Coach Report layer 1 — the sentence check (docs/10_AI_Design.md §10.3.1-10.3.6).

Grades what one learner said in one session: grammar, vocabulary, a paraphrase,
and the natural version.

Most of this file is about NOT calling the model. The two cost decisions in
§10.3.3-10.3.4 do more than any model choice:

1. **Filter in plain Python first.** "yeah", "ok", "I think so" carry nothing to
   grade. In a normal session this drops roughly half the segments, for free.
2. **Reuse by content hash.** Learners repeat the same broken phrase constantly;
   a sentence already graded is never paid for twice.

Then batch 20 sentences per call, which turns a 60-sentence session from 60 API
calls into 3.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections.abc import Iterable, Sequence

from app.ai.errors import ProviderError
from app.ai.metering import BudgetExceeded
from app.ai.ports import LLMProvider, LLMRequest
from app.ai.routing import Route
from app.models.feedback import SentenceFeedback
from app.models.transcript import TranscriptSegment
from app.repositories.feedback import FeedbackRepository
from app.schemas.feedback import FeedbackBatch, SentenceVerdict
from app.services.prompts import SENTENCE_CHECK_SYSTEM, normalise_level

logger = logging.getLogger(__name__)

#: Sentences per API call (§10.3.4). The system prompt is written once instead
#: of 20 times, and the per-request overhead disappears.
BATCH_SIZE = 20

#: Below this, a line carries nothing worth grading. Raising it to 6 is the
#: first cost lever to pull, and it is free (§10.9).
MIN_WORDS = 4

#: Whole-line fillers. Matched against the normalised line, not word-by-word, so
#: "I think so" is skipped but "I think so because it helps me relax" is not.
FILLERS = frozenset(
    {
        "yeah", "yes", "no", "ok", "okay", "right", "sure", "exactly", "really",
        "i think so", "i see", "me too", "of course", "thank you", "thanks",
        "i dont know", "i don't know", "not really", "you know", "i agree",
    }
)

_PUNCT = re.compile(r"[^\w\s']")
_SPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse spaces.

    Used for BOTH the filler check and the cache key, so "I go there." and
    "i go there" are recognised as the same sentence a learner said twice.
    """
    return _SPACE.sub(" ", _PUNCT.sub("", text.lower())).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def worth_assessing(text: str, seen: set[str] | None = None) -> bool:
    """Whether this line is worth spending a model on. Free; runs before any call."""
    cleaned = normalise(text)
    if not cleaned:
        return False
    if cleaned in FILLERS:
        return False
    if len(cleaned.split()) < MIN_WORDS:
        return False
    if seen is not None:
        digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        if digest in seen:
            return False  # said twice in the same session; grade it once
        seen.add(digest)
    return True


def select_segments(segments: Iterable[TranscriptSegment]) -> list[TranscriptSegment]:
    """Drop everything not worth grading, keeping the first of any repeat."""
    seen: set[str] = set()
    return [s for s in segments if worth_assessing(s.text, seen)]


def chunk(items: Sequence[TranscriptSegment], size: int = BATCH_SIZE):
    for start in range(0, len(items), size):
        yield items[start : start + size]


class FeedbackService:
    def __init__(
        self, llm: LLMProvider, route: Route, feedback: FeedbackRepository
    ) -> None:
        self._llm = llm
        self._route = route
        self._feedback = feedback

    async def assess(
        self,
        user_id: uuid.UUID,
        segments: Sequence[TranscriptSegment],
        level: str | None = None,
        room_id: uuid.UUID | None = None,
    ) -> list[SentenceFeedback]:
        """Grade one learner's segments, reusing anything already graded.

        Returns the rows for every gradeable sentence — cached and fresh alike —
        so the caller does not have to care which came from where.
        """
        candidates = select_segments(segments)
        if not candidates:
            return []

        # Reuse first. A learner who repeats a phrase across sessions should not
        # be billed for it twice.
        cached = await self._feedback.find_by_hashes(
            user_id, [text_hash(s.text) for s in candidates]
        )
        results = list(cached.values())
        todo = [s for s in candidates if text_hash(s.text) not in cached]
        if cached:
            logger.info(
                "Feedback cache hit on %d/%d sentences", len(cached), len(candidates)
            )
        if not todo:
            return results

        cefr = normalise_level(level)
        for batch in chunk(todo):
            verdicts = await self._grade(batch, cefr)
            if verdicts is None:
                break  # provider is down or capped; keep what we have
            results.extend(
                await self._store(user_id, room_id, batch, verdicts)
            )
        return results

    async def _grade(
        self, batch: Sequence[TranscriptSegment], cefr: str
    ) -> list[SentenceVerdict] | None:
        """One API call for up to 20 sentences, or ``None`` if it could not run."""
        numbered = "\n".join(f"{i}. {s.text}" for i, s in enumerate(batch))
        try:
            response = await self._llm.generate(
                LLMRequest(
                    system=SENTENCE_CHECK_SYSTEM.format(level=cefr),
                    user=numbered,
                    max_tokens=self._route.max_tokens,
                    timeout_s=self._route.timeout_s,
                    effort=self._route.effort,
                    schema=FeedbackBatch,
                )
            )
        except BudgetExceeded as exc:
            logger.info("Feedback stopped by a spend cap: %s", exc)
            return None
        except ProviderError as exc:
            logger.warning("Feedback batch failed: %s", exc)
            return None

        parsed = response.parsed
        if not isinstance(parsed, FeedbackBatch):
            # The stub cannot invent a valid schema instance, and a provider that
            # returns nothing usable is no better than one that is down.
            logger.warning("Feedback returned no structured output (%s)", response.model)
            return None

        self._last_model = response.model
        return parsed.items

    async def _store(
        self,
        user_id: uuid.UUID,
        room_id: uuid.UUID | None,
        batch: Sequence[TranscriptSegment],
        verdicts: Sequence[SentenceVerdict],
    ) -> list[SentenceFeedback]:
        model = getattr(self, "_last_model", "unknown")
        rows: list[SentenceFeedback] = []
        for verdict in verdicts:
            # The model returns the index it was given. Ignore anything out of
            # range rather than trusting it to line up — a shifted index would
            # attach one learner's feedback to a different sentence.
            if not 0 <= verdict.index < len(batch):
                logger.warning("Feedback index %s out of range, skipping", verdict.index)
                continue
            segment = batch[verdict.index]
            rows.append(
                await self._feedback.add(
                    SentenceFeedback(
                        user_id=user_id,
                        room_id=room_id or segment.room_id,
                        segment_id=segment.id,
                        original_text=segment.text,
                        text_hash=text_hash(segment.text),
                        is_correct=verdict.is_correct,
                        corrected=verdict.corrected,
                        natural=verdict.natural,
                        paraphrase=verdict.paraphrase,
                        errors=[e.model_dump() for e in verdict.errors],
                        vocab=[v.model_dump() for v in verdict.vocab],
                        cefr=verdict.cefr[:4] if verdict.cefr else None,
                        score=max(0, min(100, verdict.score)),
                        model=model,
                    )
                )
            )
        return rows
