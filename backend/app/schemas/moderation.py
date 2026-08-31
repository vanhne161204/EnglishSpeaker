"""Schemas for room owner moderation (PRD §8.3 owner controls)."""

import uuid
from enum import StrEnum

from pydantic import BaseModel


class ModerationAction(StrEnum):
    """What the owner wants to do to a member."""

    mute = "mute"
    unmute = "unmute"
    kick = "kick"


class ModerateRequest(BaseModel):
    """An owner-issued moderation command against one member of a room."""

    # NOTE: there is deliberately no `owner_id`. The caller is taken from the
    # session token — a body-supplied owner id let ANY caller kick ANY member of
    # ANY room, because the check compared a database value against a number the
    # attacker chose (docs/11_Security.md §11.4).
    target_user_id: uuid.UUID
    action: ModerationAction


class ModerateResult(BaseModel):
    ok: bool
    action: ModerationAction
    target_user_id: uuid.UUID
