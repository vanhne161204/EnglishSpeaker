"""Objective speech metrics from transcript timestamps (docs §10.3.8).

You cannot see hesitation in text. You *can* see it in timestamps, and
``transcript_segments.spoken_at`` already stores them.

This module is pure Python — no API call, no model. That is the point: these
numbers are **measured**, so the band report reasons from evidence instead of
guessing fluency from a paragraph. The difference is between a model saying
"sounds like a 6" and one reasoning "104 wpm with 7 long pauses and 14-word
turns is Band 5 territory, because the descriptor requires speaking *at length*".

### Honest limits

``spoken_at`` is when the engine **finalised** a sentence, not when the speaker
started it. That means pure *speaking* time cannot be separated from pauses, so
this module does not pretend to: an earlier version estimated segment durations
from word counts and then computed a rate from both, which is circular and
produced impossible figures like 900 wpm.

What is left is genuinely measurable — gaps, turn lengths, word counts — plus a
rate over **elapsed** session time. When even that comes out implausible (a very
short session, or segments finalised in a burst), ``rate_is_reliable`` is False
and the prompt says the rate is unmeasurable rather than quoting a number the
model would reason from.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.models.transcript import TranscriptSegment

#: Gaps above this count as a *noticeable* pause — the Band 4/5 descriptor's
#: "cannot respond without noticeable pauses".
LONG_PAUSE_S = 3.0
#: A session shorter than this cannot give a meaningful rate.
MIN_SESSION_SECONDS = 10.0
#: Above this, the timestamps are not describing real speech — segments finalised
#: in a burst, or a wrong client clock. Reported as unmeasurable rather than as a
#: number, for the same reason pronunciation is not scored: a wrong figure the
#: model reasons from is worse than an absent one.
IMPLAUSIBLE_WPM = 250.0

#: Hesitation markers. Speech-to-text keeps most of these verbatim.
FILLERS = (
    "um", "uh", "erm", "ah", "hmm", "mm", "er",
    "you know", "i mean", "sort of", "kind of", "like i said",
)

#: Phrases a speaker uses when repairing what they just said.
SELF_CORRECTION = ("i mean", "sorry", "no wait", "actually no", "or rather", "let me")

#: Subordination — what separates "a mix of simple and complex structures"
#: (Band 6) from "subordinate structures are rare" (Band 4).
COMPLEX_MARKERS = (
    "because", "although", "though", "while", "whereas", "unless", "since",
    "which", "who", "whom", "whose", "that", "if", "when", "before", "after",
    "so that", "even though", "in order to",
)

#: Discourse markers. Range here is the "uses a range of connectives" descriptor;
#: deliberately excludes bare and/but/so, which everyone uses at every band.
LINKERS = (
    "however", "also", "actually", "basically", "anyway", "besides", "finally",
    "first", "firstly", "then", "moreover", "therefore", "for example",
    "for instance", "in fact", "on the other hand", "as well", "in addition",
    "by the way", "of course", "at least", "instead",
)

_WORD = re.compile(r"[a-z']+")


@dataclass(frozen=True, slots=True)
class SpeechMetrics:
    """What was measured. Every field is computed, never estimated by a model."""

    #: Words per minute of ELAPSED session time, not of pure speaking time.
    #:
    #: Only sentence-finalisation timestamps are available, so true speaking
    #: duration cannot be separated from pauses — any attempt to estimate it is
    #: circular (duration guessed from word count, then rate computed from both).
    #: Elapsed-time rate is genuinely measurable, and for IELTS it is arguably
    #: the better signal anyway: it captures speed AND hesitation together.
    #: In a balanced two-person conversation, 60-100 is normal.
    words_per_minute: float
    #: False when the session was too short, or the numbers came out impossible.
    #: The prompt then says the rate is unmeasurable instead of quoting a figure.
    rate_is_reliable: bool
    session_seconds: float
    turn_count: int
    total_words: int
    mean_words_per_turn: float
    #: IELTS Part 2 expects ~180+ words in one turn; this exposes stopping early.
    longest_turn_words: int
    filler_rate: float  # per 100 words
    self_correction_count: int
    long_pause_count: int
    type_token_ratio: float
    complex_clause_ratio: float  # share of turns using subordination
    linker_variety: int  # distinct discourse markers used

    def as_prompt_block(self) -> str:
        """Render for the band prompt, with the reference ranges an examiner uses.

        The comparisons matter as much as the numbers: "104 wpm" means nothing to
        a model that does not know native conversation runs 140-180.
        """
        # An unreliable rate is reported as unmeasurable rather than as a number.
        # Same principle as not scoring pronunciation: a wrong figure the model
        # reasons from is worse than an absent one.
        rate = (
            f"{self.words_per_minute:.0f} words/min of elapsed time   "
            "(60-100 is normal for a balanced two-person conversation)"
            if self.rate_is_reliable
            else (
                "not measurable from these timestamps — ignore speed and judge "
                "fluency from turn length and pauses instead"
            )
        )
        return (
            "MEASURED (computed from timestamps, not your estimate — trust these):\n"
            f"  speech rate ......... {rate}\n"
            f"  session length ...... {self.session_seconds:.0f}s\n"
            f"  turns ............... {self.turn_count}\n"
            f"  mean words/turn ..... {self.mean_words_per_turn:.0f}\n"
            f"  longest turn ........ {self.longest_turn_words} words   "
            "(speaking at length starts around 40+)\n"
            f"  fillers ............. {self.filler_rate:.1f} per 100 words\n"
            f"  self-corrections .... {self.self_correction_count}\n"
            f"  pauses over {LONG_PAUSE_S:.0f}s ..... {self.long_pause_count}\n"
            f"  type-token ratio .... {self.type_token_ratio:.2f}   "
            "(vocabulary range; lower means more repetition)\n"
            f"  complex clauses ..... {self.complex_clause_ratio:.0%} of turns\n"
            f"  linker variety ...... {self.linker_variety} distinct"
        )


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _count_phrases(lowered: str, phrases: Sequence[str]) -> int:
    return sum(lowered.count(phrase) for phrase in phrases)


def _seconds_between(earlier: datetime, later: datetime) -> float:
    # SQLite drops tzinfo even on DateTime(timezone=True); Postgres keeps it.
    # Compare like with like rather than crashing on a mixed pair.
    if (earlier.tzinfo is None) != (later.tzinfo is None):
        earlier = earlier.replace(tzinfo=None)
        later = later.replace(tzinfo=None)
    return (later - earlier).total_seconds()


def compute(segments: Sequence[TranscriptSegment]) -> SpeechMetrics:
    """Measure one speaker's fluency from their own segments, oldest first."""
    ordered = sorted(segments, key=lambda s: s.spoken_at)
    if not ordered:
        return SpeechMetrics(
            words_per_minute=0.0, rate_is_reliable=False, session_seconds=0.0,
            turn_count=0, total_words=0, mean_words_per_turn=0.0,
            longest_turn_words=0, filler_rate=0.0, self_correction_count=0,
            long_pause_count=0, type_token_ratio=0.0, complex_clause_ratio=0.0,
            linker_variety=0,
        )

    per_turn = [_words(s.text) for s in ordered]
    counts = [len(w) for w in per_turn]
    total_words = sum(counts)

    # Pauses are directly measurable: a gap between two of this speaker's own
    # finalised sentences that is longer than a natural breath.
    long_pauses = sum(
        1
        for previous, current in zip(ordered, ordered[1:], strict=False)
        if _seconds_between(previous.spoken_at, current.spoken_at) > LONG_PAUSE_S
    )

    session_seconds = _seconds_between(ordered[0].spoken_at, ordered[-1].spoken_at)
    wpm = (total_words / session_seconds * 60) if session_seconds > 0 else 0.0

    lowered = " ".join(s.text.lower() for s in ordered)
    all_words = [word for turn in per_turn for word in turn]
    unique = len(set(all_words))

    complex_turns = sum(
        1
        for segment in ordered
        if any(marker in segment.text.lower() for marker in COMPLEX_MARKERS)
    )
    linkers_used = {linker for linker in LINKERS if linker in lowered}

    return SpeechMetrics(
        words_per_minute=min(wpm, IMPLAUSIBLE_WPM),
        # A one-turn session, or segments finalised in a burst, cannot give a
        # believable rate. Flag it so the prompt does not quote it as fact.
        rate_is_reliable=(
            session_seconds >= MIN_SESSION_SECONDS and 0 < wpm <= IMPLAUSIBLE_WPM
        ),
        session_seconds=session_seconds,
        turn_count=len(ordered),
        total_words=total_words,
        mean_words_per_turn=total_words / len(ordered),
        longest_turn_words=max(counts),
        filler_rate=(_count_phrases(lowered, FILLERS) / total_words * 100)
        if total_words
        else 0.0,
        self_correction_count=_count_phrases(lowered, SELF_CORRECTION),
        long_pause_count=long_pauses,
        # Type-token ratio falls as a text gets longer, so it compares fairly
        # only between sessions of similar length. Treat it as a hint, not a score.
        type_token_ratio=(unique / total_words) if total_words else 0.0,
        complex_clause_ratio=complex_turns / len(ordered),
        linker_variety=len(linkers_used),
    )
