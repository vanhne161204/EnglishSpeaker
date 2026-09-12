"""Reads and writes for Shadowing (PRD §8.14)."""

from __future__ import annotations

import uuid

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shadowing import ShadowingAttempt, ShadowingClip, ShadowingVideo


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
        self,
        user_id: uuid.UUID,
        topic_id: uuid.UUID | None = None,
        *,
        video_id: uuid.UUID | None = None,
    ) -> dict[str, tuple[int, int]]:
        """item_key -> (best score, number of tries), for one learner in one topic
        or one video."""
        where = (
            ShadowingAttempt.video_id == video_id
            if video_id is not None
            else ShadowingAttempt.topic_id == topic_id
        )
        stmt = (
            select(ShadowingAttempt.item_key, func.max(ShadowingAttempt.score), func.count())
            .where(ShadowingAttempt.user_id == user_id, where)
            .group_by(ShadowingAttempt.item_key)
        )
        rows = (await self.session.execute(stmt)).all()
        return {key: (int(best), int(tries)) for key, best, tries in rows}

    async def practised_by_video(self, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """video_id -> how many of its sentences this learner has tried."""
        stmt = (
            select(ShadowingAttempt.video_id, func.count(distinct(ShadowingAttempt.item_key)))
            .where(ShadowingAttempt.user_id == user_id, ShadowingAttempt.video_id.is_not(None))
            .group_by(ShadowingAttempt.video_id)
        )
        rows = (await self.session.execute(stmt)).all()
        return {video_id: int(count) for video_id, count in rows if video_id is not None}

    # --- videos (Phase 4) ---------------------------------------------------

    async def list_videos(self, *, published_only: bool) -> list[ShadowingVideo]:
        stmt = select(ShadowingVideo).order_by(ShadowingVideo.created_at.desc())
        if published_only:
            stmt = stmt.where(ShadowingVideo.status == "published")
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_video(self, video_id: uuid.UUID) -> ShadowingVideo | None:
        return await self.session.get(ShadowingVideo, video_id)

    async def add_video(self, video: ShadowingVideo) -> ShadowingVideo:
        self.session.add(video)
        await self.session.flush()
        return video

    async def delete_video(self, video: ShadowingVideo) -> None:
        await self.session.delete(video)
        await self.session.flush()
