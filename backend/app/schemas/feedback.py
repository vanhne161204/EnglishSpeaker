"""Coach Report layer 1 schemas (docs/10_AI_Design.md §10.3.5).

``FeedbackBatch`` is handed to the model as a structured-output schema, so the
API guarantees the shape — no JSON parsing, and no "the model wrote prose
instead" failure mode.

Field ORDER matters in the model-facing types. The model fills fields in the
order they appear, so anything that should be *reasoned from* comes before the
verdict it supports.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# --- what the model returns ----------------------------------------------


class GrammarError(BaseModel):
    """One real grammar mistake. Not style, not awkwardness."""

    wrong: str = Field(description="The exact wrong words, quoted from the sentence.")
    right: str = Field(description="The fix.")
    kind: str = Field(description='e.g. "verb tense", "article", "preposition".')
    why: str = Field(description="At most 12 words, plain English.")


class VocabUpgrade(BaseModel):
    basic: str = Field(description="The weak word the learner used.")
    better: str = Field(description="A stronger word at their level + 1.")
    example: str = Field(description="Their sentence, rewritten with the better word.")


class SentenceVerdict(BaseModel):
    """The model's judgement on one sentence."""

    index: int = Field(description="Which numbered input sentence this is for.")
    # Errors first: naming the mistakes before declaring correctness stops the
    # model committing to a verdict and then rationalising it.
    errors: list[GrammarError]
    vocab: list[VocabUpgrade]
    is_correct: bool
    corrected: str | None = Field(description="Null when is_correct is true.")
    natural: str = Field(description="How a native speaker would say it out loud.")
    paraphrase: str = Field(description="Same meaning, different structure.")
    cefr: str = Field(description='"A1".."C2".')
    score: int = Field(description="0-100.")


class FeedbackBatch(BaseModel):
    """One API call's worth of verdicts — 20 sentences (§10.3.4)."""

    items: list[SentenceVerdict]


# --- what the API returns -------------------------------------------------


class SentenceFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID | None
    segment_id: uuid.UUID | None
    original_text: str
    is_correct: bool
    corrected: str | None
    natural: str
    paraphrase: str
    errors: list[GrammarError]
    vocab: list[VocabUpgrade]
    cefr: str | None
    score: int
    model: str
    created_at: datetime


class FeedbackJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID | None
    status: str
    total: int
    done: int
    error: str | None


class MistakeCount(BaseModel):
    """One repeated mistake and how often it happened."""

    kind: str
    count: int


class FeedbackSummary(BaseModel):
    """The view a learner actually returns for: *"what do I keep getting wrong?"*

    Pure SQL over stored rows — no AI call, so it costs nothing to show (§10.5).
    """

    sentences_checked: int
    with_errors: int
    average_score: float
    top_mistakes: list[MistakeCount]
