"""Room membership (join/leave) schemas."""

from pydantic import BaseModel, Field


class JoinRequest(BaseModel):
    # NOTE: no `user_id`. The actor is the authenticated caller — see
    # docs/11_Security.md §11.1: the server decides who you are.
    # Optional override so incognito rooms can show a temporary alias instead of
    # the user's real profile name.
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    # Required only for password-protected rooms; ignored for public ones.
    password: str | None = Field(default=None, max_length=72)

# NOTE: leaving takes no body at all. It used to carry `user_id`, which let a
# caller remove somebody else from a room.
