"""Data-access for IELTS band reports (docs §10.3.7)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session_report import SessionReport


class SessionReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, report: SessionReport) -> SessionReport:
        self.session.add(report)
        await self.session.flush()
        return report

    async def latest_for_room(
        self, user_id: uuid.UUID, room_id: uuid.UUID
    ) -> SessionReport | None:
        """The most recent report for one session — re-running replaces, not appends."""
        stmt = (
            select(SessionReport)
            .where(SessionReport.user_id == user_id, SessionReport.room_id == room_id)
            .order_by(SessionReport.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def history(
        self, user_id: uuid.UUID, limit: int = 30
    ) -> Sequence[SessionReport]:
        """Band history, oldest-first so a chart can plot it directly.

        Progress over time is the reason a learner comes back, so this is the
        one report query that must stay cheap.
        """
        stmt = (
            select(SessionReport)
            .where(SessionReport.user_id == user_id)
            .order_by(SessionReport.created_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(reversed(rows))
