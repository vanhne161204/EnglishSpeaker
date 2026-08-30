"""Transcript schemas — the live script of a room (PRD §8.9)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: A spoken sentence is short. The cap stops a broken or hostile client from
#: pushing an essay through the socket on every keystroke of speech.
MAX_SEGMENT_CHARS = 500


class TranscriptSegmentIn(BaseModel):
    """One inbound frame from a speaking client.

    Interim frames (``final=False``) are broadcast so the room sees words appear
    live, then discarded. Only finals are stored — see the model docstring.
    """

    text: str = Field(min_length=1, max_length=MAX_SEGMENT_CHARS)
    final: bool = True
    seq: int = Field(default=0, ge=0)
    language: str | None = Field(default=None, max_length=16)
    source: str = Field(default="browser", max_length=20)
    stt_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    #: Client clock. Omitted means "now" on the server.
    spoken_at: datetime | None = None


class TranscriptSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    user_id: uuid.UUID
    speaker_name: str
    text: str
    language: str | None
    source: str
    seq: int
    spoken_at: datetime
    stt_confidence: float | None


class TranscriptPage(BaseModel):
    """A page of transcript, oldest-first so a client can append as it reads."""

    segments: list[TranscriptSegmentRead]
    #: Pass as `before` to fetch the previous page; null when at the beginning.
    next_before: datetime | None = None
