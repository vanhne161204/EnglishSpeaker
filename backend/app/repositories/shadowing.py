"""Reads and writes for Shadowing (PRD §8.14)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shadowing import ShadowingAttempt, ShadowingClip


class ShadowingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def clip_by_hash(self, text_hash: str) -> ShadowingClip | None:
        stmt = select(ShadowingClip).where(ShadowingClip.text_hash == text_hash)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_clip(self, clip: ShadowingClip) -> ShadowingClip:
        self.session.add(clip)
        await self.session.flush()
        return clip

    async def add_attempt(self, attempt: ShadowingAttempt) -> ShadowingAttempt:
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def best_scores(
        self, user_id: uuid.UUID, topic_id: uuid.UUID
    ) -> dict[str, tuple[int, int]]:
        """item_key -> (best score, number of tries), for one learner in one topic."""
        stmt = (
            select(ShadowingAttempt.item_key, func.max(ShadowingAttempt.score), func.count())
            .where(ShadowingAttempt.user_id == user_id, ShadowingAttempt.topic_id == topic_id)
            .group_by(ShadowingAttempt.item_key)
        )
        rows = (await self.session.execute(stmt)).all()
        return {key: (int(best), int(tries)) for key, best, tries in rows}
