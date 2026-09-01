"""Data-access for abuse reports (docs/11_Security.md §11.9)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.abuse_report import AbuseReport, ReportStatus


class AbuseReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, report: AbuseReport) -> AbuseReport:
        self.session.add(report)
        await self.session.flush()
        return report

    async def get(self, report_id: uuid.UUID) -> AbuseReport | None:
        return await self.session.get(AbuseReport, report_id)

    async def list(
        self, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[AbuseReport]:
        """Open reports **oldest first** — the one waiting longest is the one to
        look at. Any other status reads newest first, which is how you review
        what was recently decided."""
        stmt = select(AbuseReport)
        if status is not None:
            stmt = stmt.where(AbuseReport.status == status)
        oldest_first = status == ReportStatus.open
        order = AbuseReport.created_at.asc() if oldest_first else AbuseReport.created_at.desc()
        stmt = stmt.order_by(order).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_open(self) -> int:
        """Drives the badge on the Safety tab — an unread queue should be visible."""
        stmt = (
            select(func.count())
            .select_from(AbuseReport)
            .where(AbuseReport.status == ReportStatus.open)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_against(self, user_id: uuid.UUID) -> int:
        """How many reports name this user. One report is noise; six is a pattern."""
        stmt = (
            select(func.count())
            .select_from(AbuseReport)
            .where(AbuseReport.target_user_id == user_id)
        )
        return int((await self.session.execute(stmt)).scalar_one())
