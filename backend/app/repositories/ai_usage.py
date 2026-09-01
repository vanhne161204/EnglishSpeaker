"""Reads and writes for the AI spend ledger (docs §18.8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage import AiUsage


class AiUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, usage: AiUsage) -> AiUsage:
        self.session.add(usage)
        await self.session.flush()
        return usage

    async def spend_since(
        self, since: datetime, user_id: uuid.UUID | None = None
    ) -> Decimal:
        """Total USD spent since ``since``, for one user or the whole org."""
        stmt = select(func.coalesce(func.sum(AiUsage.cost_usd), 0)).where(
            AiUsage.created_at >= since
        )
        if user_id is not None:
            stmt = stmt.where(AiUsage.user_id == user_id)
        return Decimal(str((await self.session.execute(stmt)).scalar_one()))

    async def call_count_since(
        self, since: datetime, user_id: uuid.UUID, task: str | None = None
    ) -> int:
        """How many calls this user made since ``since`` — drives the per-task caps."""
        stmt = (
            select(func.count())
            .select_from(AiUsage)
            .where(AiUsage.created_at >= since, AiUsage.user_id == user_id)
        )
        if task is not None:
            stmt = stmt.where(AiUsage.task == task)
        return int((await self.session.execute(stmt)).scalar_one())

    async def cost_by_task(self, days: int = 7) -> list[tuple[str, Decimal, int]]:
        """(task, total cost, call count) — which feature is eating the budget."""
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = (
            select(AiUsage.task, func.sum(AiUsage.cost_usd), func.count())
            .where(AiUsage.created_at >= since)
            .group_by(AiUsage.task)
            .order_by(func.sum(AiUsage.cost_usd).desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [(task, Decimal(str(cost or 0)), count) for task, cost, count in rows]

    async def cost_per_user(
        self, days: int = 30, limit: int = 50
    ) -> list[tuple[uuid.UUID, Decimal, int]]:
        """(user, total cost, call count) — your COGS per learner.

        Everything about pricing follows from this number. The call count comes
        back with it because cost alone cannot tell a heavy user from one
        expensive call.
        """
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = (
            select(AiUsage.user_id, func.sum(AiUsage.cost_usd), func.count())
            .where(AiUsage.created_at >= since, AiUsage.user_id.is_not(None))
            .group_by(AiUsage.user_id)
            .order_by(func.sum(AiUsage.cost_usd).desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(uid, Decimal(str(cost or 0)), int(n)) for uid, cost, n in rows]

    async def daily(self, days: int = 30) -> list[tuple[str, Decimal, int]]:
        """(YYYY-MM-DD, cost, calls) oldest first — the trend line.

        Days with no calls are filled in as zero here rather than in the UI: a
        chart that silently skips quiet days compresses time and makes a spike
        look like a plateau.
        """
        since = (datetime.now(UTC) - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # `date()` is the one function SQLite and Postgres spell the same way for
        # this; `date_trunc` would not work on SQLite (dev).
        day = func.date(AiUsage.created_at)
        stmt = (
            select(day, func.sum(AiUsage.cost_usd), func.count())
            .where(AiUsage.created_at >= since)
            .group_by(day)
        )
        found = {
            str(d): (Decimal(str(cost or 0)), int(n))
            for d, cost, n in (await self.session.execute(stmt)).all()
        }

        out: list[tuple[str, Decimal, int]] = []
        for offset in range(days):
            key = (since + timedelta(days=offset)).strftime("%Y-%m-%d")
            cost, calls = found.get(key, (Decimal(0), 0))
            out.append((key, cost, calls))
        return out

    async def recent(
        self,
        limit: int = 50,
        offset: int = 0,
        *,
        task: str | None = None,
        user_id: uuid.UUID | None = None,
        failed_only: bool = False,
    ) -> list[AiUsage]:
        """The raw ledger, newest first.

        Aggregates answer "how much"; this answers "which call". When one figure
        looks wrong, the only way to find out why is to read the individual rows
        that produced it.
        """
        stmt = select(AiUsage)
        if task:
            stmt = stmt.where(AiUsage.task == task)
        if user_id is not None:
            stmt = stmt.where(AiUsage.user_id == user_id)
        if failed_only:
            stmt = stmt.where(AiUsage.ok.is_(False))
        stmt = stmt.order_by(AiUsage.created_at.desc()).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_calls(self, days: int = 30) -> int:
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = select(func.count()).select_from(AiUsage).where(AiUsage.created_at >= since)
        return int((await self.session.execute(stmt)).scalar_one())

    async def health(self, hours: int = 24) -> list[tuple[str, int, int, int]]:
        """(model, calls, degraded, failed) — a rising degraded rate is an outage."""
        since = datetime.now(UTC) - timedelta(hours=hours)
        stmt = (
            select(
                AiUsage.model,
                func.count(),
                func.sum(cast(AiUsage.degraded, Integer)),
                func.sum(1 - cast(AiUsage.ok, Integer)),
            )
            .where(AiUsage.created_at >= since)
            .group_by(AiUsage.model)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(m, int(c), int(d or 0), int(f or 0)) for m, c, d, f in rows]
