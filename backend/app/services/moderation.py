"""Per-room ban registry for owner moderation (PRD §8.3 owner controls).

When an owner kicks a member, the member is banned from rejoining that room. The
ban list is process-local and in-memory — fine for the demo and a single API
instance; a multi-instance deployment would back this with Redis (the interface
here would stay the same).
"""

import uuid
from collections import defaultdict

# room_id -> set of banned user_ids. Kept as strings to match the ids that arrive
# on WebSocket query params without repeated parsing.
_bans: dict[str, set[str]] = defaultdict(set)


def ban(room_id: uuid.UUID | str, user_id: uuid.UUID | str) -> None:
    """Ban ``user_id`` from ``room_id`` (idempotent)."""
    _bans[str(room_id)].add(str(user_id))


def is_banned(room_id: uuid.UUID | str, user_id: uuid.UUID | str) -> bool:
    """Whether ``user_id`` is currently banned from ``room_id``."""
    return str(user_id) in _bans.get(str(room_id), set())


def clear_room(room_id: uuid.UUID | str) -> None:
    """Drop all bans for a room (used when tearing a room down or in tests)."""
    _bans.pop(str(room_id), None)
