"""Matchmaking: find a room for a user, or create one (PRD §8.4, §8.5, §8.6).

MVP strategy is synchronous "find-or-create": we look for a suitable open room
and return it; if none exists we create one for the user to wait in. This needs
no background worker and is demoable solo. A real waiting queue can replace it
later behind the same endpoints.

Match conditions (PRD §8.6): mode is required; topic is preferred, then level.
We try the most specific combination first and fall back step by step. (Interest
matching is user-to-user and not modelled at the room level yet.)
"""

from app.models.enums import RoomKind
from app.models.room import Room
from app.repositories.room import RoomRepository
from app.schemas.match import MatchRequest


class MatchService:
    def __init__(self, rooms: RoomRepository) -> None:
        self.rooms = rooms

    async def match_one(self, req: MatchRequest) -> Room:
        room = await self._find_open(req, RoomKind.one_on_one)
        if room is not None:
            return room
        return await self._create_room(req, RoomKind.one_on_one, capacity=2)

    async def random_match(self, req: MatchRequest) -> Room:
        # Any open room in the same mode; create a group room if none has space.
        room = await self._find_open(req, kind=None)
        if room is not None:
            return room
        return await self._create_room(req, RoomKind.group, capacity=4)

    async def _find_open(self, req: MatchRequest, kind: RoomKind | None) -> Room | None:
        """Try open rooms in decreasing preference (PRD §8.6).

        Order: topic+level → topic → interest+level → interest → level → any. The
        interest tiers let us still find a relevant room when the exact topic is
        unavailable, before falling back to level-only or any open room.
        """
        seen: set[tuple[str | None, str | None]] = set()
        for topic, level in (
            (req.topic, req.level),
            (req.topic, None),
            (req.interest, req.level),
            (req.interest, None),
            (None, req.level),
            (None, None),
        ):
            key = (topic, level)
            if key in seen:
                continue
            seen.add(key)
            room = await self.rooms.find_open_match(req.mode, kind, topic=topic, level=level)
            if room is not None:
                return room
        return None

    async def _create_room(self, req: MatchRequest, kind: RoomKind, capacity: int) -> Room:
        label = req.topic or ("Free Talk" if kind is RoomKind.one_on_one else "Open Room")
        prefix = "1-on-1: " if kind is RoomKind.one_on_one else ""
        room = Room(
            title=f"{prefix}{label}",
            mode=req.mode.value,
            kind=kind.value,
            topic=req.topic,
            level=req.level,
            status="open",
            capacity=capacity,
            participant_count=0,
        )
        return await self.rooms.add(room)
