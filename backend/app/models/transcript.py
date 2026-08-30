"""TranscriptSegment model — one finalised sentence of speech (PRD §8.9).

The written record of what each person actually SAID in a room, as opposed to
``Message`` which is what they typed. Two reasons these are separate tables:

* Volume. Speech produces roughly ten times the rows of chat, and nobody wants
  their transcript flooding the chat history.
* Meaning. A transcript line is evidence about the speaker's English; a chat
  message is a thing they chose to send. Only the first is worth grading.

This table is the input to the whole Coach Report feature (docs/10_AI_Design.md
§10.3) — layer 1 reads `text`, layer 2 reads `spoken_at` for the fluency metrics
and `stt_confidence` for the pronunciation hint list.

**Only finalised segments are stored.** Interim (partial) results fly over the
WebSocket so the UI can show words appearing live, but persisting them would
multiply writes by ~15x for text that is immediately replaced.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TranscriptSegment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transcript_segments"

    __table_args__ = (
        # Room playback, and the "last N on join" query every client runs.
        Index("ix_transcript_room_spoken", "room_id", "spoken_at"),
        # "My speaking history", newest first (PRD §8.9 review-after).
        Index("ix_transcript_user_spoken", "user_id", "spoken_at"),
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Snapshot, for the same reason as Message.sender_name: the transcript must
    # stay readable if someone later changes their display name.
    speaker_name: Mapped[str] = mapped_column(String(80), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    # BCP-47-ish, e.g. "en-US". What the engine reported, not what we asked for.
    language: Mapped[str | None] = mapped_column(String(16), default=None)

    # Which engine produced this: browser | whisper | deepgram | stub.
    # Kept because accuracy differs sharply between them, and a later analysis
    # of "why is this learner's feedback poor" usually starts here.
    source: Mapped[str] = mapped_column(
        String(20), default="browser", server_default="browser", nullable=False
    )

    # Client-side counter, unique per speaker per connection. Lets the UI replace
    # an interim line with its final version instead of appending a duplicate.
    seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # When the words were spoken, by the CLIENT's clock. `created_at` is the
    # server's. Both are kept: the client clock can be wrong, but it is the only
    # thing that measures the GAP between segments, which is what the fluency
    # metrics in §10.3.8 are computed from.
    spoken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Engine confidence 0-1, when reported. Captured now even though nothing
    # reads it until the pronunciation work (§10.3.11): once a session ends the
    # engine's score is gone, and it cannot be backfilled.
    stt_confidence: Mapped[float | None] = mapped_column(Float, default=None)
