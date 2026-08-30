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
    ) -> list[tuple[uuid.UUID, Decimal]]:
        """Your COGS, per user. Everything about pricing follows from this."""
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = (
            select(AiUsage.user_id, func.sum(AiUsage.cost_usd))
            .where(AiUsage.created_at >= since, AiUsage.user_id.is_not(None))
            .group_by(AiUsage.user_id)
            .order_by(func.sum(AiUsage.cost_usd).desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(uid, Decimal(str(cost or 0))) for uid, cost in rows]

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
