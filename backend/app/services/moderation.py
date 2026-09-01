"""Room bans — who may not rejoin which room (PRD §8.3, docs/11_Security.md Step 4).

This module used to be a process-local ``dict``. It is now backed by the
``room_bans`` table, which changes three things that mattered:

* a ban survives a deploy (this project deploys on every push to main);
* a ban **expires** — an owner's kick is a time-out, not a life sentence;
* a ban can be lifted, by the owner or by an admin.

The functions here open their own session only where the caller has none (the
WebSocket handshake). Everywhere else, pass the request's session so the ban
check joins the surrounding transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.room_ban import RoomBan
from app.repositories.room_ban import RoomBanRepository


def default_expiry(hours: int) -> datetime | None:
    """When an owner's kick should lapse. ``hours <= 0`` means permanent."""
    if hours <= 0:
        return None
    return datetime.now(UTC) + timedelta(hours=hours)


async def is_banned(session: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await RoomBanRepository(session).is_banned(room_id, user_id)


async def is_banned_standalone(room_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Ban check for the WebSocket handshake, which has no request session.

    Mirrors ``deps.authenticate_socket``: a socket is not a request, so it opens
    a short-lived session of its own rather than holding one for the life of the
    connection.
    """
    async with AsyncSessionLocal() as session:
        return await is_banned(session, room_id, user_id)


async def ban(
    session: AsyncSession,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    banned_by: uuid.UUID | None = None,
    reason: str | None = None,
    expires_at: datetime | None = None,
) -> RoomBan:
    """Ban (or re-ban) a user from a room. ``expires_at=None`` is permanent."""
    return await RoomBanRepository(session).upsert(
        room_id, user_id, banned_by=banned_by, reason=reason, expires_at=expires_at
    )


async def clear_room(session: AsyncSession, room_id: uuid.UUID) -> None:
    """Drop every ban for a room (tearing a room down, and tests)."""
    await RoomBanRepository(session).clear_room(room_id)
