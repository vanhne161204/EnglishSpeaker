"""Coach Report layer 2 — the IELTS band report (docs §10.3.7-10.3.14).

Layer 1 tells a learner *"this sentence was wrong."* That is a proofreader. This
answers the question they actually care about: **what band am I, why, and what
do I do this week to get half a band more?**

The order of operations matters:

1. **Measure** fluency from timestamps, in Python (§10.3.8). Never ask the model
   to guess speed or hesitation from a paragraph.
2. **Pair** each of the learner's turns with the one partner line that prompted
   it, so "did you actually answer?" is judgeable (§10.3.0).
3. **Ask** the model, with the band descriptors in the prompt and evidence
   demanded before every number (§10.3.10, §10.3.13).
4. **Verify** that every evidence quote is the learner's own words — in code,
   not by trusting a prompt rule.
5. **Compute** the overall band ourselves, with IELTS rounding, from the three
   criteria that can honestly be scored.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from app.ai.errors import ProviderError
from app.ai.metering import BudgetExceeded
from app.ai.ports import LLMProvider, LLMRequest
from app.ai.routing import Route
from app.models.session_report import SessionReport
from app.models.transcript import TranscriptSegment
from app.repositories.session_report import SessionReportRepository
from app.schemas.ielts import IeltsReport, ReportMode
from app.services import speech_metrics
from app.services.bands import clamp, next_band, overall_band
from app.services.ielts_context import build_turns, render_turns, strip_foreign_quotes
from app.services.prompts import IELTS_REPORT_SYSTEM

logger = logging.getLogger(__name__)

#: Below this, there is not enough speech to say anything useful about a band.
#: A three-word session would otherwise produce a confident, meaningless number.
MIN_WORDS_FOR_A_BAND = 40


class NotEnoughSpeech(Exception):
    """Raised when a session is too short to band honestly."""


class ReportUnavailable(Exception):
    """The model could not produce a report (down, capped, or unusable output)."""


class IeltsService:
    def __init__(
        self, llm: LLMProvider, route: Route, reports: SessionReportRepository
    ) -> None:
        self._llm = llm
        self._route = route
        self._reports = reports

    async def build_report(
        self,
        user_id: uuid.UUID,
        segments: Sequence[TranscriptSegment],
        room_id: uuid.UUID | None = None,
        mode: ReportMode = ReportMode.conversation,
        include_partner: bool = True,
    ) -> SessionReport:
        mine = [s for s in segments if s.user_id == user_id]
        metrics = speech_metrics.compute(mine)
        if metrics.total_words < MIN_WORDS_FOR_A_BAND:
            raise NotEnoughSpeech(
                f"Speak a bit more first — about {MIN_WORDS_FOR_A_BAND} words are needed "
                f"for a fair estimate (you said {metrics.total_words})."
            )

        turns = build_turns(segments, user_id, include_partner=include_partner)
        report = await self._ask(metrics, turns, mode)

        # Enforce the privacy rule in code. The model has no idea which lines are
        # sensitive, so a prompt rule alone is not enough (§10.3.0).
        report, removed = strip_foreign_quotes(report, [s.text for s in mine])
        if removed:
            logger.warning(
                "Removed %d evidence quote(s) that were not the learner's own words", removed
            )

        fluency = clamp(report.fluency.band)
        lexical = clamp(report.lexical.band)
        grammar = clamp(report.grammar.band)
        # Three criteria, not four. Pronunciation cannot be scored from text, and
        # inventing it would make every overall band quietly wrong (§10.3.11).
        overall = overall_band(fluency, lexical, grammar)

        return await self._reports.add(
            SessionReport(
                user_id=user_id,
                room_id=room_id,
                mode=mode.value,
                band_fluency=fluency,
                band_lexical=lexical,
                band_grammar=grammar,
                band_pronunciation=None,
                band_overall=overall,
                pronunciation_assessed=False,
                overall_is_estimate=True,
                summary=report.summary,
                next_band=next_band(overall),
                criteria={
                    "fluency": report.fluency.model_dump(),
                    "lexical": report.lexical.model_dump(),
                    "grammar": report.grammar.model_dump(),
                },
                blockers=[b.model_dump(mode="json") for b in report.blockers],
                drills=[d.model_dump() for d in report.drills],
                metrics=_metrics_dict(metrics),
                model=getattr(self, "_last_model", "unknown"),
                quotes_removed=removed,
            )
        )

    async def _ask(self, metrics, turns, mode: ReportMode) -> IeltsReport:
        # Measured numbers and the transcript go in the USER message: they change
        # every session, so keeping them out of the system prompt leaves the
        # descriptor block a stable, cacheable prefix (§18.3 `cache_system`).
        user = (
            f"{metrics.as_prompt_block()}\n\n"
            f"SESSION TYPE: {mode.value}"
            f"{'' if mode.is_exam_like else ' (free conversation, not an exam task)'}\n\n"
            f"TRANSCRIPT:\n{render_turns(turns)}"
        )
        try:
            response = await self._llm.generate(
                LLMRequest(
                    system=IELTS_REPORT_SYSTEM,
                    user=user,
                    max_tokens=self._route.max_tokens,
                    timeout_s=self._route.timeout_s,
                    effort=self._route.effort,
                    cache_system=self._route.cache_system,
                    schema=IeltsReport,
                )
            )
        except BudgetExceeded as exc:
            raise ReportUnavailable(exc.detail) from exc
        except ProviderError as exc:
            logger.warning("Band report failed: %s", exc)
            raise ReportUnavailable("The coach is unavailable right now.") from exc

        if not isinstance(response.parsed, IeltsReport):
            # A band with no structured output behind it would be a number we
            # made up. Refuse rather than store one.
            raise ReportUnavailable("The coach could not produce a report.")

        self._last_model = response.model
        return response.parsed


def _metrics_dict(metrics: speech_metrics.SpeechMetrics) -> dict:
    return {
        "words_per_minute": round(metrics.words_per_minute, 1),
        "rate_is_reliable": metrics.rate_is_reliable,
        "session_seconds": round(metrics.session_seconds, 1),
        "turn_count": metrics.turn_count,
        "total_words": metrics.total_words,
        "mean_words_per_turn": round(metrics.mean_words_per_turn, 1),
        "longest_turn_words": metrics.longest_turn_words,
        "filler_rate": round(metrics.filler_rate, 2),
        "self_correction_count": metrics.self_correction_count,
        "long_pause_count": metrics.long_pause_count,
        "type_token_ratio": round(metrics.type_token_ratio, 3),
        "complex_clause_ratio": round(metrics.complex_clause_ratio, 3),
        "linker_variety": metrics.linker_variety,
    }
