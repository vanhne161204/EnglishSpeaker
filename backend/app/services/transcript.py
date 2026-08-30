"""Transcript service — turning spoken frames into stored, shareable script.

The rules that keep this cheap and safe live here rather than in the WebSocket
handler, so they are testable without a socket (PRD §8.9).

Two decisions shape everything:

* **Only finals are stored.** Interim results are broadcast so the room watches
  words appear, then dropped. Storing them would multiply writes ~15x for text
  that is replaced a second later.
* **Speech is throttled per speaker.** A stuck client, or someone leaving a
  radio next to their mic, must not be able to fill the table. The cap is per
  user per room, in memory, and deliberately generous for real speech.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime

from app.models.transcript import TranscriptSegment
from app.repositories.transcript import TranscriptRepository
from app.schemas.transcript import TranscriptSegmentIn

#: Finalised segments allowed per speaker per minute. Natural speech produces
#: roughly 10-20; 60 leaves headroom for a fast talker and still stops a loop.
MAX_FINALS_PER_MINUTE = 60
_WINDOW_SECONDS = 60.0

#: (room_id, user_id) -> timestamps of recent finalised segments.
_recent: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _throttled(room_id: str, user_id: str) -> bool:
    """Whether this speaker has exceeded their finalised-segment budget."""
    key = (room_id, user_id)
    now = time.monotonic()
    hits = _recent[key]
    cutoff = now - _WINDOW_SECONDS
    while hits and hits[0] <= cutoff:
        hits.popleft()
    if len(hits) >= MAX_FINALS_PER_MINUTE:
        return True
    hits.append(now)
    return False


def forget_speaker(room_id: str, user_id: str) -> None:
    """Drop a speaker's throttle state when they leave, so the dict cannot grow
    without bound across a long-running process."""
    _recent.pop((room_id, user_id), None)


class TranscriptService:
    def __init__(self, transcripts: TranscriptRepository) -> None:
        self._transcripts = transcripts

    async def record_final(
        self,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
        speaker_name: str,
        payload: TranscriptSegmentIn,
    ) -> TranscriptSegment | None:
        """Persist one finalised segment, or return ``None`` if throttled.

        Returning ``None`` rather than raising: hitting the cap is not an error
        the speaker should see mid-conversation, it is a line we quietly drop.
        """
        if _throttled(str(room_id), str(user_id)):
            return None

        text = payload.text.strip()
        if not text:
            return None

        return await self._transcripts.add(
            TranscriptSegment(
                room_id=room_id,
                user_id=user_id,
                speaker_name=speaker_name,
                text=text,
                language=payload.language,
                source=payload.source,
                seq=payload.seq,
                # Trust the client's clock only for ordering within a speaker's
                # own stream; fall back to the server's when it is absent.
                spoken_at=payload.spoken_at or datetime.now(UTC),
                stt_confidence=payload.stt_confidence,
            )
        )
