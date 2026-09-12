"""Admin side of Shadowing video lessons (PRD §8.14 Phase 4).

An admin gives a YouTube link, types the sentences, and marks where each one
starts and ends. Nothing here ever fetches the video: YouTube's terms forbid
downloading it, so the only thing stored about it is its id.
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import parse_qs, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, BadRequestError, NotFoundError
from app.models.enums import ContentStatus
from app.models.shadowing import ShadowingSegment, ShadowingVideo
from app.models.user import User
from app.repositories.audit import AuditRepository
from app.repositories.shadowing import ShadowingRepository
from app.schemas.shadowing import (
    ShadowingVideoAdminDetail,
    ShadowingVideoAdminRead,
    ShadowingVideoCreate,
    ShadowingVideoUpdate,
    VideoSegmentIn,
    VideoSegmentRead,
    VideoSegmentsSave,
)

#: A YouTube video id: 11 characters from this set.
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"}
#: youtube.com/<one of these>/<id>
_ID_PATHS = {"embed", "shorts", "live", "v"}

#: Under 0.3 s is a click, not a sentence. 30 s is Azure's limit for a check.
MIN_SEGMENT_MS = 300
MAX_SEGMENT_MS = 30_000
MAX_SEGMENT_WORDS = 40


class VideoNotReady(AppError):
    """Publishing needs a source note and at least one sentence."""

    status_code = 400
    code = "video_not_ready"


def parse_youtube_id(value: str) -> str:
    """The 11-character video id from a YouTube link, or the id itself."""
    text = value.strip()
    if _YOUTUBE_ID.fullmatch(text):
        return text
    url = urlparse(text if "://" in text else f"https://{text}")
    host = (url.hostname or "").lower().removeprefix("www.")
    candidate = ""
    if host == "youtu.be":
        candidate = url.path.strip("/").split("/")[0]
    elif host in _YOUTUBE_HOSTS:
        parts = [part for part in url.path.split("/") if part]
        if parts == ["watch"]:
            candidate = parse_qs(url.query).get("v", [""])[0]
        elif len(parts) >= 2 and parts[0] in _ID_PATHS:
            candidate = parts[1]
    if _YOUTUBE_ID.fullmatch(candidate):
        return candidate
    raise BadRequestError("That is not a link to a YouTube video.")


def _check_segment(number: int, row: VideoSegmentIn) -> None:
    length = row.end_ms - row.start_ms
    if length < MIN_SEGMENT_MS:
        raise BadRequestError(f"Sentence {number}: the end must be at least 0.3 s after the start.")
    if length > MAX_SEGMENT_MS:
        raise BadRequestError(f"Sentence {number}: a sentence can be at most 30 seconds long.")
    if not 1 <= len(row.text.split()) <= MAX_SEGMENT_WORDS:
        raise BadRequestError(f"Sentence {number}: a sentence has 1 to 40 words.")


def _read(video: ShadowingVideo) -> ShadowingVideoAdminRead:
    return ShadowingVideoAdminRead(
        id=video.id,
        youtube_id=video.youtube_id,
        title=video.title,
        level=video.level,
        source_note=video.source_note,
        status=video.status,  # type: ignore[arg-type]  # validated by pydantic
        sentences=len(video.segments),
        created_at=video.created_at,
        updated_at=video.updated_at,
    )


def _detail(video: ShadowingVideo) -> ShadowingVideoAdminDetail:
    segments = sorted(video.segments, key=lambda segment: segment.position)
    return ShadowingVideoAdminDetail(
        **_read(video).model_dump(),
        segments=[VideoSegmentRead.model_validate(segment) for segment in segments],
    )


class ShadowingVideoAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ShadowingRepository(session)
        self.audit = AuditRepository(session)

    async def list(self) -> list[ShadowingVideoAdminRead]:
        return [_read(video) for video in await self.repo.list_videos(published_only=False)]

    async def get(self, video_id: uuid.UUID) -> ShadowingVideoAdminDetail:
        return _detail(await self._video(video_id))

    async def create(self, actor: User, payload: ShadowingVideoCreate) -> ShadowingVideoAdminDetail:
        video = ShadowingVideo(
            youtube_id=parse_youtube_id(payload.youtube),
            title=payload.title.strip(),
            level=payload.level or None,
            source_note=payload.source_note.strip(),
            status=ContentStatus.draft,
            created_by=actor.id,
        )
        await self.repo.add_video(video)
        await self._record(actor, "video.create", video, f"YouTube {video.youtube_id}")
        return await self._fresh(video)

    async def update(
        self, actor: User, video_id: uuid.UUID, payload: ShadowingVideoUpdate
    ) -> ShadowingVideoAdminDetail:
        video = await self._video(video_id)
        changes = payload.model_dump(exclude_unset=True)
        if changes.get("title"):
            video.title = changes["title"].strip()
        if "level" in changes:
            video.level = changes["level"] or None
        if changes.get("source_note") is not None:
            video.source_note = changes["source_note"].strip()
        if changes.get("status"):
            video.status = changes["status"]
        if video.status == ContentStatus.published:
            self._check_ready(video)
        await self.session.flush()
        detail = ", ".join(f"status={video.status}" if key == "status" else key for key in changes)
        await self._record(actor, "video.update", video, detail or "no change")
        return await self._fresh(video)

    async def save_segments(
        self, actor: User, video_id: uuid.UUID, payload: VideoSegmentsSave
    ) -> ShadowingVideoAdminDetail:
        """Replace the video's sentences with ``payload``, in time order.

        A sentence sent with its id keeps that id, so its item key, and every
        learner's best score on it, survive the save. A sentence left out is deleted.
        """
        video = await self._video(video_id)
        # Numbered as the admin sees them, before sorting.
        for number, row in enumerate(payload.segments, start=1):
            _check_segment(number, row)

        existing = {segment.id: segment for segment in video.segments}
        kept: list[ShadowingSegment] = []
        rows = sorted(payload.segments, key=lambda row: (row.start_ms, row.end_ms))
        for position, row in enumerate(rows):
            segment = existing.pop(row.id, None) if row.id is not None else None
            if segment is None:
                segment = ShadowingSegment()
            segment.position = position
            segment.start_ms = row.start_ms
            segment.end_ms = row.end_ms
            segment.text = " ".join(row.text.split())
            segment.translation = (row.translation or "").strip() or None
            kept.append(segment)
        # delete-orphan removes the sentences left out.
        video.segments = kept
        if video.status == ContentStatus.published:
            self._check_ready(video)
        await self.session.flush()
        await self._record(actor, "video.sentences", video, f"{len(kept)} sentences")
        return await self._fresh(video)

    async def delete(self, actor: User, video_id: uuid.UUID) -> None:
        video = await self._video(video_id)
        await self._record(actor, "video.delete", video, f"YouTube {video.youtube_id}")
        await self.repo.delete_video(video)

    # --- internals ---------------------------------------------------------

    async def _video(self, video_id: uuid.UUID) -> ShadowingVideo:
        video = await self.repo.get_video(video_id)
        if video is None:
            raise NotFoundError("Video not found")
        return video

    async def _fresh(self, video: ShadowingVideo) -> ShadowingVideoAdminDetail:
        # The database sets created_at / updated_at; load them (and the segments,
        # in order) rather than touching expired attributes under asyncio.
        await self.session.refresh(video)
        return _detail(video)

    @staticmethod
    def _check_ready(video: ShadowingVideo) -> None:
        if not video.source_note.strip():
            raise VideoNotReady(
                "Add where the video comes from and why we may use it before publishing."
            )
        if not video.segments:
            raise VideoNotReady("Add at least one sentence before publishing.")

    async def _record(self, actor: User, action: str, video: ShadowingVideo, detail: str) -> None:
        await self.audit.record(
            actor_id=actor.id,
            actor_name=actor.display_name,
            action=action,
            target_type="shadowing_video",
            target_id=video.id,
            target_name=video.title,
            detail=detail,
        )
