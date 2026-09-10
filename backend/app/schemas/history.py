"""Practice history schemas (PRD §8.13)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class HistoryItem(BaseModel):
    """One conversation the learner joined, with a summary of their own feedback.

    Room fields are nullable because a room can be deleted after the fact. Its
    conversation goes with it, but the learner's band report survives, and
    History still shows that (``room_exists`` is then false).
    """

    room_id: uuid.UUID | None
    room_title: str | None
    topic: str | None
    level: str | None
    mode: str | None
    kind: str | None
    room_exists: bool

    first_joined_at: datetime
    last_seen_at: datetime
    #: How many times the learner joined. Unknown for a deleted room.
    visits: int | None

    #: Lines of the live script that were the learner's own.
    lines_spoken: int
    #: Coach report layer 1, the learner's own sentences only.
    sentences_checked: int
    sentences_with_mistakes: int

    #: Coach report layer 2. A JSON number, not a Decimal: Decimal serialises as
    #: a string, and the frontend formats bands with `toFixed`.
    band_overall: float | None
    band_is_estimate: bool | None
    report_summary: str | None
    #: A stable key for deleted-room entries, which have no room id.
    report_id: uuid.UUID | None
