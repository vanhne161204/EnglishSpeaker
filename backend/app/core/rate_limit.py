"""Lightweight in-memory rate limiting for sensitive endpoints.

A fixed set of timestamps per (path, client-IP) key implements a sliding window:
requests older than the window are dropped, and if too many remain the caller
gets 429. Good enough for a single-process launch (login/register throttling).

Limitations (fine for now, revisit when scaling out):
- In-memory, so limits are per-process and reset on restart. Move the counters
  to Redis when you run more than one worker/replica.
- Keyed by client IP. Behind a reverse proxy, set the proxy to forward
  ``X-Forwarded-For`` (read below) and ensure only the trusted proxy can set it.
"""

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request

from app.core.exceptions import AppError

# path+ip -> timestamps of recent hits (seconds).
_hits: dict[str, deque[float]] = defaultdict(deque)


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


def _client_ip(request: Request) -> str:
    # Trust X-Forwarded-For only if a proxy sets it; take the first (original) IP.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limiter(
    max_requests: int, window_seconds: int
) -> Callable[[Request], Awaitable[None]]:
    """Build a FastAPI dependency that allows ``max_requests`` per window per IP."""

    async def dependency(request: Request) -> None:
        key = f"{request.url.path}:{_client_ip(request)}"
        now = time.monotonic()
        hits = _hits[key]
        # Drop timestamps outside the window.
        cutoff = now - window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= max_requests:
            raise RateLimitError("Too many attempts. Please wait a moment and try again.")
        hits.append(now)

    return dependency
