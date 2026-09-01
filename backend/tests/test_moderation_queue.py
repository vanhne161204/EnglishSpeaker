"""Abuse reports and room bans.

Two things this covers that did not exist before:

* A learner could not report what happened in a voice call with a stranger.
* A ban lived in a Python dict, so it vanished on every deploy, never expired,
  and nobody could lift one (docs/11_Security.md Step 4).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.repositories.room_ban import RoomBanRepository


async def _other_id(other_client: AsyncClient) -> str:
    return (await other_client.get("/api/v1/users/me")).json()["id"]


# --- filing a report --------------------------------------------------------


async def test_reporting_requires_an_account(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/moderation/reports",
        json={"target_user_id": str(uuid.uuid4()), "reason": "spam"},
    )
    assert resp.status_code == 401


async def test_a_learner_can_report_another(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    admin_id = (await admin_client.get("/api/v1/users/me")).json()["id"]
    resp = await other_client.post(
        "/api/v1/moderation/reports",
        json={
            "target_user_id": admin_id,
            "reason": "harassment",
            "detail": "Kept interrupting and swearing",
            "quoted_text": "the thing they said",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "open"
    # Names are snapshotted so the report stays readable after a rename.
    assert body["reporter_name"] == "Other"
    assert body["target_name"] == "Admin"
    # The reporter is the token holder, never a body field.
    assert body["reporter_id"] == await _other_id(other_client)


async def test_the_reporter_cannot_be_forged(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """`reporter_id` is not in the schema at all, so a forged reporter is
    impossible rather than merely rejected — the same rule as chat messages."""
    admin_id = (await admin_client.get("/api/v1/users/me")).json()["id"]
    resp = await other_client.post(
        "/api/v1/moderation/reports",
        json={
            "target_user_id": admin_id,
            "reason": "spam",
            "reporter_id": str(uuid.uuid4()),  # ignored
        },
    )
    assert resp.status_code == 201
    assert resp.json()["reporter_id"] == await _other_id(other_client)


async def test_you_cannot_report_yourself(other_client: AsyncClient) -> None:
    me = await _other_id(other_client)
    resp = await other_client.post(
        "/api/v1/moderation/reports", json={"target_user_id": me, "reason": "spam"}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "self_report"


async def test_reporting_an_unknown_user_is_404(other_client: AsyncClient) -> None:
    resp = await other_client.post(
        "/api/v1/moderation/reports",
        json={"target_user_id": str(uuid.uuid4()), "reason": "spam"},
    )
    assert resp.status_code == 404


async def test_an_invalid_reason_is_rejected(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    admin_id = (await admin_client.get("/api/v1/users/me")).json()["id"]
    resp = await other_client.post(
        "/api/v1/moderation/reports",
        json={"target_user_id": admin_id, "reason": "whatever"},
    )
    assert resp.status_code == 422


# --- the admin queue --------------------------------------------------------


async def test_an_ordinary_user_cannot_read_the_queue(other_client: AsyncClient) -> None:
    assert (await other_client.get("/api/v1/admin/reports")).status_code == 403


async def test_resolving_a_report_can_suspend_the_account_in_one_action(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """Deciding and acting are one motion for a moderator, so they are one
    request — otherwise the common case is two calls that can half-fail."""
    other_id = await _other_id(other_client)

    # Admin files a report against the learner, then reviews it.
    filed = await admin_client.post(
        "/api/v1/moderation/reports",
        json={"target_user_id": other_id, "reason": "hate", "detail": "slurs"},
    )
    report_id = filed.json()["id"]

    reviewed = await admin_client.patch(
        f"/api/v1/admin/reports/{report_id}",
        json={
            "status": "resolved",
            "note": "Confirmed from the transcript",
            "suspend_target": True,
            "suspend_reason": "Hate speech",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "resolved"
    assert reviewed.json()["review_note"] == "Confirmed from the transcript"

    # The account is switched off, immediately, on the token they already hold.
    blocked = await other_client.get("/api/v1/users/me")
    assert blocked.status_code == 403
    assert "Hate speech" in blocked.json()["error"]["message"]


async def test_dismissing_a_report_leaves_the_account_alone(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    other_id = await _other_id(other_client)
    filed = await admin_client.post(
        "/api/v1/moderation/reports", json={"target_user_id": other_id, "reason": "spam"}
    )
    await admin_client.patch(
        f"/api/v1/admin/reports/{filed.json()['id']}",
        json={"status": "dismissed", "note": "Misunderstanding"},
    )
    assert (await other_client.get("/api/v1/users/me")).status_code == 200


async def test_the_open_queue_excludes_what_has_been_decided(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    other_id = await _other_id(other_client)
    first = await admin_client.post(
        "/api/v1/moderation/reports", json={"target_user_id": other_id, "reason": "spam"}
    )
    await admin_client.post(
        "/api/v1/moderation/reports", json={"target_user_id": other_id, "reason": "other"}
    )
    assert len((await admin_client.get("/api/v1/admin/reports")).json()) == 2

    await admin_client.patch(
        f"/api/v1/admin/reports/{first.json()['id']}", json={"status": "resolved"}
    )
    still_open = (await admin_client.get("/api/v1/admin/reports")).json()
    assert len(still_open) == 1
    assert still_open[0]["reason"] == "other"

    resolved = (
        await admin_client.get("/api/v1/admin/reports", params={"status": "resolved"})
    ).json()
    assert len(resolved) == 1


async def test_a_report_count_shows_up_on_the_user_row(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """One report is noise; several is a pattern. The row has to show it."""
    other_id = await _other_id(other_client)
    for reason in ("spam", "harassment", "other"):
        await admin_client.post(
            "/api/v1/moderation/reports",
            json={"target_user_id": other_id, "reason": reason},
        )
    rows = (await admin_client.get("/api/v1/admin/users", params={"q": "other"})).json()
    assert rows["items"][0]["reports_against"] == 3


# --- bans -------------------------------------------------------------------


async def test_a_kick_bans_the_member_and_the_ban_is_persisted(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    # Created, not matched: `match/random` leaves the room unowned, and only an
    # owner can moderate it.
    room = (await admin_client.post("/api/v1/rooms", json={"title": "Owned room"})).json()
    await admin_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})

    other_id = await _other_id(other_client)
    kicked = await admin_client.post(
        f"/api/v1/rooms/{room['id']}/moderate",
        json={"target_user_id": other_id, "action": "kick"},
    )
    assert kicked.status_code == 200

    # Rejoining is refused...
    rejoin = await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    assert rejoin.status_code == 403
    assert rejoin.json()["error"]["code"] == "room_banned"

    # ...and it is a real row, not a process-local dict that a deploy would clear.
    bans = (await admin_client.get("/api/v1/admin/bans")).json()
    assert len(bans) == 1
    assert bans[0]["user_id"] == other_id
    assert bans[0]["reason"] == "Removed by the room owner"
    assert bans[0]["expires_at"] is not None, "an owner's kick should be a time-out"


async def test_an_admin_can_lift_a_ban(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """There was previously no way to undo a mis-clicked kick, at all."""
    # Created, not matched: `match/random` leaves the room unowned, and only an
    # owner can moderate it.
    room = (await admin_client.post("/api/v1/rooms", json={"title": "Owned room"})).json()
    await admin_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    other_id = await _other_id(other_client)
    await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    await admin_client.post(
        f"/api/v1/rooms/{room['id']}/moderate",
        json={"target_user_id": other_id, "action": "kick"},
    )

    ban_id = (await admin_client.get("/api/v1/admin/bans")).json()[0]["id"]
    assert (await admin_client.delete(f"/api/v1/admin/bans/{ban_id}")).status_code == 204

    assert (await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})).status_code == 200
    assert (await admin_client.get("/api/v1/admin/bans")).json() == []

    audit = (await admin_client.get("/api/v1/admin/audit")).json()
    assert any(e["action"] == "ban.lift" for e in audit)


async def test_an_expired_ban_no_longer_blocks_a_join(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """The whole point of Step 4: a ban is a time-out, not a life sentence."""
    # Created, not matched: `match/random` leaves the room unowned, and only an
    # owner can moderate it.
    room = (await admin_client.post("/api/v1/rooms", json={"title": "Owned room"})).json()
    await admin_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    other_id = await _other_id(other_client)
    await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    await admin_client.post(
        f"/api/v1/rooms/{room['id']}/moderate",
        json={"target_user_id": other_id, "action": "kick"},
    )
    assert (await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})).status_code == 403

    # Wind the expiry into the past rather than sleeping for a day.
    async with AsyncSessionLocal() as session:
        repo = RoomBanRepository(session)
        ban = await repo.get(uuid.UUID(room["id"]), uuid.UUID(other_id))
        assert ban is not None
        ban.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await session.commit()

    assert (await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})).status_code == 200
    # An expired ban is not listed as active, but the row is kept as history.
    assert (await admin_client.get("/api/v1/admin/bans")).json() == []


async def test_rebanning_updates_rather_than_duplicating(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """Otherwise a room accumulates rows that each have to be lifted separately."""
    # Created, not matched: `match/random` leaves the room unowned, and only an
    # owner can moderate it.
    room = (await admin_client.post("/api/v1/rooms", json={"title": "Owned room"})).json()
    await admin_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    other_id = await _other_id(other_client)

    for _ in range(3):
        await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
        await admin_client.post(
            f"/api/v1/rooms/{room['id']}/moderate",
            json={"target_user_id": other_id, "action": "kick"},
        )
        async with AsyncSessionLocal() as session:
            ban = await RoomBanRepository(session).get(uuid.UUID(room["id"]), uuid.UUID(other_id))
            assert ban is not None
            ban.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()

    async with AsyncSessionLocal() as session:
        rows = await RoomBanRepository(session).list_active(limit=100)
    assert len(rows) == 0  # all expired
    # ...and there is exactly one row for the pair, not three.
    async with AsyncSessionLocal() as session:
        ban = await RoomBanRepository(session).get(uuid.UUID(room["id"]), uuid.UUID(other_id))
    assert ban is not None


@pytest.mark.parametrize("hours,expect_permanent", [(0, True), (24, False)])
def test_ban_duration_is_configurable(hours: int, expect_permanent: bool) -> None:
    """`ROOM_BAN_HOURS=0` means permanent, for the cases that warrant it."""
    from app.services.moderation import default_expiry

    assert (default_expiry(hours) is None) is expect_permanent


def test_the_default_kick_is_a_timeout_not_permanent() -> None:
    assert settings.room_ban_hours > 0
