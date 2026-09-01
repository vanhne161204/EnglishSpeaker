"""Data-access for the admin audit log.

Writes only ever append; there is deliberately no update or delete method. See
``app/models/admin_audit.py``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit import AdminAuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        actor_id: uuid.UUID | None,
        actor_name: str,
        action: str,
        target_type: str = "",
        target_id: uuid.UUID | None = None,
        target_name: str = "",
        detail: str | None = None,
    ) -> AdminAuditLog:
        entry = AdminAuditLog(
            actor_id=actor_id,
            actor_name=actor_name,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            detail=detail,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list(self, limit: int = 100, offset: int = 0) -> list[AdminAuditLog]:
        stmt = (
            select(AdminAuditLog)
            .order_by(AdminAuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())
