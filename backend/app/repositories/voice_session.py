"""Reads and writes for AI voice coach sessions (PRD §8.12)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.voice_session import AiVoiceSession


class VoiceSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, row: AiVoiceSession) -> AiVoiceSession:
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, session_id: uuid.UUID) -> AiVoiceSession | None:
        return await self.session.get(AiVoiceSession, session_id)

    async def list_since(self, user_id: uuid.UUID, since: datetime) -> list[AiVoiceSession]:
        """This user's sessions started since ``since``, oldest first."""
        stmt = (
            select(AiVoiceSession)
            .where(AiVoiceSession.user_id == user_id, AiVoiceSession.created_at >= since)
            .order_by(AiVoiceSession.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_unsettled(self, user_id: uuid.UUID, now: datetime) -> list[AiVoiceSession]:
        """Sessions past their expiry that nobody ended — the tab closed or crashed."""
        stmt = select(AiVoiceSession).where(
            AiVoiceSession.user_id == user_id,
            AiVoiceSession.ended_at.is_(None),
            AiVoiceSession.expires_at <= now,
        )
        return list((await self.session.execute(stmt)).scalars().all())
