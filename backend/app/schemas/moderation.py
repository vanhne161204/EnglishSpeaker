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

    # The caller, who must be the room's owner. This is the lightweight-identity
    # user id (there is no auth token in this version).
    owner_id: uuid.UUID
    target_user_id: uuid.UUID
    action: ModerationAction


class ModerateResult(BaseModel):
    ok: bool
    action: ModerationAction
    target_user_id: uuid.UUID
