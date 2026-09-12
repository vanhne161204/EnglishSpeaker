"""Schemas for Shadowing (PRD §8.14, docs/08_API.md "Shadowing")."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

ShadowingKind = Literal["question", "answer", "term", "example"]
WordStatus = Literal["ok", "close", "wrong", "missed"]
Tempo = Literal["slow", "good", "fast"]


class ShadowingItem(BaseModel):
    #: "<kind>-<uuid>", stable for as long as the source row exists.
    key: str
    kind: ShadowingKind
    text: str
    translation: str | None
    #: An admin-attached recording. When null, fetch .../items/{key}/audio.
    audio_url: str | None
    best_score: int | None
    attempts: int


class ShadowingItemList(BaseModel):
    topic_id: uuid.UUID
    topic_title: str
    level: str | None
    #: False when the server cannot make model voices: use the browser's voice.
    voice_enabled: bool
    #: Phase 2: whether the "Check pronunciation" button works, and how many
    #: checks this learner has left today.
    assess_enabled: bool = False
    assess_remaining: int = 0
    items: list[ShadowingItem]


class ShadowingAttemptCreate(BaseModel):
    topic_id: uuid.UUID
    item_key: str = Field(max_length=80)
    heard_text: str = Field(default="", max_length=1000)
    #: How long the learner spoke, from the first to the last loud moment.
    duration_ms: int | None = Field(default=None, ge=0, le=60_000)
    #: How long the model voice is at normal speed.
    reference_ms: int | None = Field(default=None, ge=0, le=60_000)
    engine: Literal["browser", "server"] = "browser"


class WordResult(BaseModel):
    #: The word as written in the sentence.
    word: str
    #: What was heard in its place, or null when it was missed.
    heard: str | None
    status: WordStatus


class ShadowingResult(BaseModel):
    #: Word match 0-100. NOT a pronunciation score.
    score: int
    words: list[WordResult]
    #: Words heard that are not in the sentence.
    extra: list[str]
    tempo_ratio: float | None
    tempo: Tempo | None
    best_score: int
    attempts: int


# --- Phase 2: deep pronunciation check (Azure) ------------------------------


class PronunciationWord(BaseModel):
    word: str
    accuracy: float | None
    #: Azure's terms: None, Mispronunciation, Omission, Insertion.
    error: str
    #: A name or non-English word: shown, but not counted in `accuracy`.
    is_name: bool


class PronunciationResult(BaseModel):
    #: Mean word accuracy WITHOUT names (0-100).
    accuracy: float | None
    fluency: float | None
    completeness: float | None
    #: Null when the prosody add-on is off.
    prosody: float | None
    words: list[PronunciationWord]
    #: What Azure recognised. Biased toward the sentence in scripted mode.
    heard: str
    seconds: float
    remaining_today: int
