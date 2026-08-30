"""IELTS band report schemas (docs §10.3.9).

**Field order is load-bearing.** A model fills fields in the order they appear,
so `CriterionScore` puts evidence, then what worked, then what held them back,
then the descriptor — and only then the band. Reversing those two measurably
inflates scores: the model picks a number first and rationalises it after.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReportMode(StrEnum):
    """A free-flowing room is not an IELTS test, and the report must say so."""

    conversation = "conversation"
    ielts_part1 = "ielts_part1"
    ielts_part2 = "ielts_part2"
    ielts_part3 = "ielts_part3"

    @property
    def is_exam_like(self) -> bool:
        """Whether a band from this mode is trustworthy enough to call a band."""
        return self is not ReportMode.conversation


class Criterion(StrEnum):
    fluency = "fluency"
    lexical = "lexical"
    grammar = "grammar"
    pronunciation = "pronunciation"


# --- what the model returns ----------------------------------------------


class CriterionScore(BaseModel):
    evidence: list[str] = Field(
        max_length=3, description="Exact quotes from the LEARNER's own lines."
    )
    what_worked: str = Field(description="At most 25 words.")
    what_held_back: str = Field(description="At most 25 words.")
    descriptor: str = Field(description="The band descriptor wording it best matches.")
    band: float = Field(description="0-9 in half steps. Decide this LAST.")


class Blocker(BaseModel):
    """One specific thing between this learner and the next half band."""

    title: str
    example: str = Field(description="Their own words, quoted.")
    fix: str = Field(description="The same idea, said better.")
    criterion: Criterion


class Drill(BaseModel):
    """Homework. Doable this week, alone, in under 15 minutes."""

    title: str
    how: str = Field(description="At most 40 words, concrete steps.")
    minutes: int


class IeltsReport(BaseModel):
    """One session's band report.

    Pronunciation is absent by design: no Claude or GPT model accepts audio, so
    it cannot be scored from a transcript (§10.3.11). The service computes the
    overall from the three criteria that CAN be measured and flags it as an
    estimate — it never asks the model to guess a pronunciation band.
    """

    fluency: CriterionScore
    lexical: CriterionScore
    grammar: CriterionScore

    summary: str = Field(description="At most 60 words, warm, plain English.")
    blockers: list[Blocker] = Field(max_length=3)
    drills: list[Drill] = Field(max_length=3)


# --- what the API returns -------------------------------------------------


class SessionReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID | None
    mode: str

    band_fluency: Decimal
    band_lexical: Decimal
    band_grammar: Decimal
    band_pronunciation: Decimal | None
    band_overall: Decimal

    pronunciation_assessed: bool
    #: True while `overall` averages only Fluency/Lexical/Grammar. The UI MUST
    #: label the number when this is set.
    overall_is_estimate: bool

    summary: str
    next_band: Decimal
    criteria: dict
    blockers: list[Blocker]
    drills: list[Drill]
    metrics: dict
    model: str
    #: How many evidence quotes were NOT the learner's own words and had to be
    #: removed. Non-zero means the prompt's role separation is slipping — it
    #: feeds the admin review queue (§10.8), so it must reach the API.
    quotes_removed: int
    created_at: datetime


class BandPoint(BaseModel):
    """One point on the progress chart."""

    created_at: datetime
    band_overall: Decimal
    mode: str
