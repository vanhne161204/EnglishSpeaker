"""Whose words go into the band report (docs §10.3.0).

Only the learner's own lines are scored. But Fluency & Coherence is partly
*"did you actually answer the question, and did you develop it?"*, and that
cannot be judged from::

    "Yes, I like it."

without knowing whether the question was *"Do you like coffee?"* (fine) or
*"Why do you think coffee culture changed in Vietnam?"* (a Band 4 non-answer).
A real examiner hears the question. So must the model.

The rules that make that safe:

1. Only the ONE partner turn immediately before each of the learner's turns —
   not the whole room history, which triples the input for almost no signal.
2. Roles are labelled unmistakably, and the prompt says to score only ``[LEARNER]``.
3. Evidence quotes are verified against the learner's own text after parsing.
   A prompt rule alone is not enough: the model has no idea which sentences are
   privacy-sensitive. That check is :func:`strip_foreign_quotes`.
4. Partner text is never written to ``session_reports``. It exists in one
   prompt, then it is gone.
5. Incognito rooms get no partner context at all.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from app.models.transcript import TranscriptSegment
from app.schemas.ielts import IeltsReport

_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s']")

LEARNER_TAG = "[LEARNER]"
PARTNER_TAG = "[partner]"


@dataclass(frozen=True, slots=True)
class Turn:
    """One of the learner's turns, with the line that prompted it (if any)."""

    prompt: TranscriptSegment | None
    mine: TranscriptSegment


def build_turns(
    segments: Sequence[TranscriptSegment],
    learner_id: uuid.UUID,
    include_partner: bool = True,
) -> list[Turn]:
    """Pair each of the learner's turns with the partner line just before it.

    ``include_partner=False`` for incognito rooms: the Fluency judgement is
    slightly weaker, which is the correct trade when the whole point of the mode
    is that nothing about the other person persists.
    """
    turns: list[Turn] = []
    previous: TranscriptSegment | None = None
    for segment in sorted(segments, key=lambda s: s.spoken_at):
        if segment.user_id == learner_id:
            turns.append(Turn(prompt=previous if include_partner else None, mine=segment))
            previous = None  # one partner line feeds one answer, not several
        else:
            previous = segment
    return turns


def render_turns(turns: Sequence[Turn]) -> str:
    """Render for the prompt with roles that cannot be confused."""
    blocks: list[str] = []
    for turn in turns:
        lines = []
        if turn.prompt is not None:
            lines.append(f"{PARTNER_TAG} {turn.prompt.text}")
        lines.append(f"{LEARNER_TAG} {turn.mine.text}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _norm(text: str) -> str:
    return _SPACE.sub(" ", _PUNCT.sub("", text.lower())).strip()


def strip_foreign_quotes(
    report: IeltsReport, learner_texts: Sequence[str]
) -> tuple[IeltsReport, int]:
    """Drop any evidence quote that is not something the learner actually said.

    Returns the cleaned report and how many quotes were removed. A non-zero count
    is worth surfacing to the admin queue (§10.8): it means partner text came
    close to leaking into a report about someone else, and the prompt's role
    separation is failing.

    Deliberately code, not a prompt rule — the model cannot know which sentences
    are privacy-sensitive.
    """
    haystack = [_norm(text) for text in learner_texts]

    def is_theirs(quote: str) -> bool:
        needle = _norm(quote)
        if not needle:
            return False
        return any(needle in hay for hay in haystack)

    removed = 0
    for criterion in (report.fluency, report.lexical, report.grammar):
        kept = [q for q in criterion.evidence if is_theirs(q)]
        removed += len(criterion.evidence) - len(kept)
        criterion.evidence = kept
    return report, removed
