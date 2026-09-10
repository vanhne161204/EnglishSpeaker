"""The Live voice port: mint a one-use token for a browser-to-vendor session.

A different shape from the other ports (docs §18.2), because the server never
sees the audio. The browser opens a WebSocket straight to the vendor. All the
server does is hand out a short-lived credential with the session's rules locked
inside it: the model, the coach instructions, the output format and a hard end
time. That keeps the real API key on the server, and makes the server — not the
browser — the one that decides how long a session may run (docs §18.13).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LiveTokenRequest:
    #: Coach instructions. Locked into the token, so the browser cannot change them.
    system_instruction: str
    #: When the vendor must stop accepting audio for this session.
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LiveToken:
    #: Opaque credential the browser passes as its API key ("auth_tokens/...").
    token: str
    #: The model the token is locked to. The browser must connect with the same one.
    model: str
    provider: str


class LiveTokenMinter(Protocol):
    name: str
    model: str

    async def mint(self, request: LiveTokenRequest) -> LiveToken: ...
