"""Practice history: the rooms a learner joined, with their own feedback (PRD §8.13).

A read across five tables, so it lives in its own repository rather than being
bolted onto one of theirs. Every query filters on the caller's user id; nothing
here can return another learner's rows.

It is one GROUP BY query per table for the whole list, never one query per room.
A learner with 50 rooms costs 5 round trips, not 250.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import SentenceFeedback
from app.models.participant import RoomParticipant
from app.models.room import Room
from app.models.session_report import SessionReport
from app.models.transcript import TranscriptSegment
from app.schemas.history import HistoryItem


def _aware(value: datetime) -> datetime:
    """Treat a naive datetime as UTC.

    SQLite returns naive datetimes and Postgres returns aware ones. Live rooms and
    deleted-room reports are merged and sorted together, and Python refuses to
    compare the two kinds. UTC is what was stored, so this is exact.
    """
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class HistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def for_user(self, user_id: uuid.UUID, limit: int = 50) -> list[HistoryItem]:
        """The learner's conversations, most recent first."""
        # A person can join the same room several times, so group the visits.
        # "Last seen" is when they last left, or joined if they never left.
        last_seen = func.max(func.coalesce(RoomParticipant.left_at, RoomParticipant.created_at))
        rooms = (
            await self.session.execute(
                select(
                    Room.id,
                    Room.title,
                    Room.topic,
                    Room.level,
                    Room.mode,
                    Room.kind,
                    func.min(RoomParticipant.created_at),
                    last_seen,
                    func.count(),
                )
                .join(Room, Room.id == RoomParticipant.room_id)
                .where(RoomParticipant.user_id == user_id)
                .group_by(Room.id, Room.title, Room.topic, Room.level, Room.mode, Room.kind)
                .order_by(last_seen.desc())
                .limit(limit)
            )
        ).all()
        room_ids = [row[0] for row in rooms]

        lines = await self._lines_spoken(user_id, room_ids)
        feedback = await self._feedback_counts(user_id, room_ids)
        reports = await self._latest_reports(user_id, room_ids)

        items: list[HistoryItem] = []
        for rid, title, topic, level, mode, kind, first, seen, visits in rooms:
            checked, wrong = feedback.get(rid, (0, 0))
            report = reports.get(rid)
            items.append(
                HistoryItem(
                    room_id=rid,
                    room_title=title,
                    topic=topic,
                    level=level,
                    mode=mode,
                    kind=kind,
                    room_exists=True,
                    first_joined_at=_aware(first),
                    last_seen_at=_aware(seen),
                    visits=int(visits),
                    lines_spoken=lines.get(rid, 0),
                    sentences_checked=checked,
                    sentences_with_mistakes=wrong,
                    band_overall=float(report.band_overall) if report else None,
                    band_is_estimate=report.overall_is_estimate if report else None,
                    report_summary=report.summary if report else None,
                    report_id=report.id if report else None,
                )
            )

        items.extend(await self._deleted_room_reports(user_id, limit))
        items.sort(key=lambda item: item.last_seen_at, reverse=True)
        return items[:limit]

    async def _lines_spoken(
        self, user_id: uuid.UUID, room_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not room_ids:
            return {}
        rows = await self.session.execute(
            select(TranscriptSegment.room_id, func.count())
            .where(TranscriptSegment.user_id == user_id, TranscriptSegment.room_id.in_(room_ids))
            .group_by(TranscriptSegment.room_id)
        )
        return {rid: int(n) for rid, n in rows.all()}

    async def _feedback_counts(
        self, user_id: uuid.UUID, room_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[int, int]]:
        """``{room: (sentences checked, sentences with a mistake)}``."""
        if not room_ids:
            return {}
        wrong = func.sum(case((SentenceFeedback.is_correct.is_(False), 1), else_=0))
        rows = await self.session.execute(
            select(SentenceFeedback.room_id, func.count(), wrong)
            .where(SentenceFeedback.user_id == user_id, SentenceFeedback.room_id.in_(room_ids))
            .group_by(SentenceFeedback.room_id)
        )
        return {rid: (int(n), int(w or 0)) for rid, n, w in rows.all() if rid is not None}

    async def _latest_reports(
        self, user_id: uuid.UUID, room_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, SessionReport]:
        """The newest band report per room. Re-running a report adds a row, so an
        older one must not win."""
        if not room_ids:
            return {}
        rows = await self.session.execute(
            select(SessionReport)
            .where(SessionReport.user_id == user_id, SessionReport.room_id.in_(room_ids))
            .order_by(SessionReport.created_at)
        )
        latest: dict[uuid.UUID, SessionReport] = {}
        for report in rows.scalars():
            if report.room_id is not None:
                latest[report.room_id] = report  # oldest first, so the newest wins
        return latest

    async def _deleted_room_reports(self, user_id: uuid.UUID, limit: int) -> list[HistoryItem]:
        """Band reports whose room was deleted.

        Deleting a room removes its conversation and its membership rows, but a
        learner's report is their own record, so it is kept with a NULL room
        (docs/11_Security.md). Without this, History would quietly drop it.
        """
        rows = await self.session.execute(
            select(SessionReport)
            .where(SessionReport.user_id == user_id, SessionReport.room_id.is_(None))
            .order_by(SessionReport.created_at.desc())
            .limit(limit)
        )
        return [
            HistoryItem(
                room_id=None,
                room_title=None,
                topic=None,
                level=None,
                mode=None,
                kind=None,
                room_exists=False,
                first_joined_at=_aware(report.created_at),
                last_seen_at=_aware(report.created_at),
                visits=None,
                lines_spoken=0,
                sentences_checked=0,
                sentences_with_mistakes=0,
                band_overall=float(report.band_overall),
                band_is_estimate=report.overall_is_estimate,
                report_summary=report.summary,
                report_id=report.id,
            )
            for report in rows.scalars()
        ]
