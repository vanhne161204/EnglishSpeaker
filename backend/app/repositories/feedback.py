"""Data-access for Coach Report layer 1 (docs/10_AI_Design.md §10.3)."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import FeedbackJob, SentenceFeedback


class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, row: SentenceFeedback) -> SentenceFeedback:
        self.session.add(row)
        await self.session.flush()
        return row

    async def find_by_hashes(
        self, user_id: uuid.UUID, hashes: Sequence[str]
    ) -> dict[str, SentenceFeedback]:
        """Already-graded sentences for this learner, keyed by content hash.

        Scoped to one user on purpose. Feedback is phrased for *their* level, so
        sharing a cache entry across learners would hand a B2 speaker advice
        written for an A2 one.
        """
        if not hashes:
            return {}
        rows = (
            (
                await self.session.execute(
                    select(SentenceFeedback).where(
                        SentenceFeedback.user_id == user_id,
                        SentenceFeedback.text_hash.in_(list(set(hashes))),
                    )
                )
            )
            .scalars()
            .all()
        )
        # Newest wins if the same sentence was graded more than once.
        out: dict[str, SentenceFeedback] = {}
        for row in sorted(rows, key=lambda r: r.created_at):
            out[row.text_hash] = row
        return out

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int = 50, before: datetime | None = None
    ) -> Sequence[SentenceFeedback]:
        stmt = select(SentenceFeedback).where(SentenceFeedback.user_id == user_id)
        if before is not None:
            stmt = stmt.where(SentenceFeedback.created_at < before)
        stmt = stmt.order_by(SentenceFeedback.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_room(
        self, user_id: uuid.UUID, room_id: uuid.UUID
    ) -> Sequence[SentenceFeedback]:
        """One learner's report for one session, in the order they spoke."""
        stmt = (
            select(SentenceFeedback)
            .where(
                SentenceFeedback.user_id == user_id,
                SentenceFeedback.room_id == room_id,
            )
            .order_by(SentenceFeedback.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def stats(self, user_id: uuid.UUID) -> tuple[int, int, float]:
        """(sentences checked, how many had errors, average score)."""
        stmt = select(
            func.count(),
            func.sum(cast(SentenceFeedback.is_correct, Integer)),
            func.avg(SentenceFeedback.score),
        ).where(SentenceFeedback.user_id == user_id)
        total, correct, average = (await self.session.execute(stmt)).one()
        total = int(total or 0)
        return total, total - int(correct or 0), float(average or 0.0)

    async def top_mistakes(self, user_id: uuid.UUID, limit: int = 5) -> list[tuple[str, int]]:
        """The mistakes this learner repeats most — the reason they come back.

        Counted in Python rather than SQL: the JSON operators differ between
        SQLite and Postgres, and one learner's rows are a bounded set. Move it
        into the database if this ever runs over the whole user base.
        """
        rows = (
            (
                await self.session.execute(
                    select(SentenceFeedback.errors).where(
                        SentenceFeedback.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        counts: Counter[str] = Counter()
        for errors in rows:
            for error in errors or []:
                kind = (error or {}).get("kind")
                if kind:
                    counts[str(kind)] += 1
        return counts.most_common(limit)

    # --- jobs -------------------------------------------------------------

    async def add_job(self, job: FeedbackJob) -> FeedbackJob:
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_job(self, job_id: uuid.UUID) -> FeedbackJob | None:
        return await self.session.get(FeedbackJob, job_id)
