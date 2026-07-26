"""Room membership (join/leave) schemas."""

import uuid

from pydantic import BaseModel, Field


class JoinRequest(BaseModel):
    user_id: uuid.UUID
    # Optional override so incognito rooms can show a temporary alias instead of
    # the user's real profile name.
    display_name: str | None = Field(default=None, min_length=1, max_length=80)


class LeaveRequest(BaseModel):
    user_id: uuid.UUID
