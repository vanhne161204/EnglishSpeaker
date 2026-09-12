"""Schemas for Shadowing (PRD §8.14, docs/08_API.md "Shadowing")."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ShadowingKind = Literal["question", "answer", "term", "example", "segment"]
WordStatus = Literal["ok", "close", "wrong", "missed"]
Tempo = Literal["slow", "good", "fast"]
VideoStatus = Literal["draft", "published", "archived"]


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
    #: Exactly one of topic_id and video_id: where the sentence comes from.
    topic_id: uuid.UUID | None = None
    video_id: uuid.UUID | None = None
    item_key: str = Field(max_length=80)
    heard_text: str = Field(default="", max_length=1000)
    #: How long the learner spoke, from the first to the last loud moment.
    duration_ms: int | None = Field(default=None, ge=0, le=60_000)
    #: How long the model voice (or the video sentence) is at normal speed.
    reference_ms: int | None = Field(default=None, ge=0, le=60_000)
    engine: Literal["browser", "server"] = "browser"

    @model_validator(mode="after")
    def _one_source(self) -> "ShadowingAttemptCreate":
        if (self.topic_id is None) == (self.video_id is None):
            raise ValueError("Give either topic_id or video_id.")
        return self


class WordResult(BaseModel):
    #: The word as written in the sentence.
    word: str
    #: What was heard in its place, or null when it was missed.
    heard: str | None
    status: WordStatus
    #: The ending the learner left off ("-s", "-ed", "-ing" or "-'s"), when the
    #: word heard is the sentence word without it. Worked out from spelling.
    hint: str | None = None


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


# --- Phase 4: video lessons ---------------------------------------------------


class ShadowingVideoCard(BaseModel):
    id: uuid.UUID
    youtube_id: str
    title: str
    level: str | None
    sentences: int
    #: How many of its sentences this learner has tried at least once.
    practised: int


class ShadowingSegmentItem(BaseModel):
    #: "segment-<uuid>".
    key: str
    text: str
    translation: str | None
    start_ms: int
    end_ms: int
    best_score: int | None
    attempts: int


class ShadowingVideoLesson(BaseModel):
    id: uuid.UUID
    youtube_id: str
    title: str
    level: str | None
    #: Where the video comes from, shown under the player.
    source_note: str
    assess_enabled: bool = False
    assess_remaining: int = 0
    items: list[ShadowingSegmentItem]


# --- Phase 4: admin -----------------------------------------------------------


class ShadowingVideoCreate(BaseModel):
    #: A YouTube link (watch, youtu.be, shorts, embed) or the 11-character id.
    youtube: str = Field(min_length=11, max_length=300)
    title: str = Field(min_length=1, max_length=200)
    level: str | None = Field(default=None, max_length=40)
    source_note: str = Field(default="", max_length=1000)


class ShadowingVideoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    level: str | None = Field(default=None, max_length=40)
    source_note: str | None = Field(default=None, max_length=1000)
    status: VideoStatus | None = None


class VideoSegmentIn(BaseModel):
    #: Set for a sentence that already exists, so its key (and the learners'
    #: scores on it) survive the save. Omit for a new sentence.
    id: uuid.UUID | None = None
    start_ms: int = Field(ge=0, le=12 * 3600 * 1000)
    end_ms: int = Field(ge=0, le=12 * 3600 * 1000)
    text: str = Field(min_length=1, max_length=400)
    translation: str | None = Field(default=None, max_length=400)


class VideoSegmentsSave(BaseModel):
    #: The whole list: a sentence left out is deleted.
    segments: list[VideoSegmentIn] = Field(max_length=300)


class VideoSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    start_ms: int
    end_ms: int
    text: str
    translation: str | None


class ShadowingVideoAdminRead(BaseModel):
    id: uuid.UUID
    youtube_id: str
    title: str
    level: str | None
    source_note: str
    status: VideoStatus
    sentences: int
    created_at: datetime
    updated_at: datetime


class ShadowingVideoAdminDetail(ShadowingVideoAdminRead):
    segments: list[VideoSegmentRead]
