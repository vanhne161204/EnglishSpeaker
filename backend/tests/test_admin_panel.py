"""The admin panel, and the rails that keep it from stranding the system.

The interesting tests here are the refusals. An admin panel that lets you demote
the last admin, or demote yourself, produces a database nobody can administer —
recoverable only by SSH and a restart. Each rail below is a state this system
could otherwise be put into and not get out of (docs/11_Security.md §11.9).
"""

import uuid

from httpx import AsyncClient


async def _user_id(client: AsyncClient) -> str:
    return (await client.get("/api/v1/users/me")).json()["id"]


async def _find(admin: AsyncClient, username: str) -> dict:
    rows = (await admin.get("/api/v1/admin/users", params={"q": username})).json()["items"]
    match = [r for r in rows if r["username"] == username]
    assert match, f"{username} not in {rows}"
    return match[0]


# --- authorization ----------------------------------------------------------


async def test_every_admin_route_rejects_an_anonymous_caller(client: AsyncClient) -> None:
    for path in ("/api/v1/admin/overview", "/api/v1/admin/users", "/api/v1/admin/ai-spend"):
        assert (await client.get(path)).status_code == 401, path


async def test_every_admin_route_rejects_an_ordinary_user(other_client: AsyncClient) -> None:
    for path in (
        "/api/v1/admin/overview",
        "/api/v1/admin/users",
        "/api/v1/admin/ai-spend",
        "/api/v1/admin/reports",
        "/api/v1/admin/bans",
        "/api/v1/admin/audit",
    ):
        assert (await other_client.get(path)).status_code == 403, path


# --- authority comes from the role column, never from a username -----------


async def test_registering_as_admin_grants_nothing(client: AsyncClient) -> None:
    """The core of the change: a USERNAME confers no authority.

    Admin used to come from an ``ADMIN_USERNAMES`` allowlist, so anyone who
    guessed the configured name and registered it got the keys. The name is now
    just a name.
    """
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "admin", "password": "pw12345678", "display_name": "Not An Admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "user"

    token = resp.json()["token"]
    blocked = await client.get(
        "/api/v1/admin/overview", headers={"Authorization": f"Bearer {token}"}
    )
    assert blocked.status_code == 403


async def test_a_demotion_survives_the_next_login(
    admin_client: AsyncClient, client: AsyncClient
) -> None:
    """Login used to re-apply the allowlist, so a demotion made in the panel
    silently reverted the next time that person signed in."""
    # A second admin, so demoting the first is allowed by the last-admin rule.
    second = await client.post(
        "/api/v1/auth/register",
        json={"username": "deputy", "password": "pw12345678", "display_name": "Deputy"},
    )
    deputy_id = second.json()["user"]["id"]
    promoted = await admin_client.patch(f"/api/v1/admin/users/{deputy_id}", json={"role": "admin"})
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    admin_id = await _user_id(admin_client)
    demoted = await client.patch(
        f"/api/v1/admin/users/{admin_id}",
        json={"role": "user"},
        headers={"Authorization": f"Bearer {second.json()['token']}"},
    )
    assert demoted.status_code == 200, demoted.text
    assert demoted.json()["role"] == "user"

    again = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin-password"}
    )
    assert again.status_code == 200
    assert again.json()["user"]["role"] == "user"


# --- rails ------------------------------------------------------------------


async def test_an_admin_cannot_change_their_own_role(admin_client: AsyncClient) -> None:
    me = await _user_id(admin_client)
    resp = await admin_client.patch(f"/api/v1/admin/users/{me}", json={"role": "user"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "self_role_change"


async def test_the_last_admin_cannot_be_demoted(
    admin_client: AsyncClient, client: AsyncClient
) -> None:
    """Even by another admin — because after the demotion there would be none."""
    second = await client.post(
        "/api/v1/auth/register",
        json={"username": "deputy", "password": "pw12345678", "display_name": "Deputy"},
    )
    deputy_id = second.json()["user"]["id"]
    await admin_client.patch(f"/api/v1/admin/users/{deputy_id}", json={"role": "admin"})

    # Deputy demotes the original admin: fine, two admins exist.
    admin_id = await _user_id(admin_client)
    deputy_auth = {"Authorization": f"Bearer {second.json()['token']}"}
    assert (
        await client.patch(
            f"/api/v1/admin/users/{admin_id}", json={"role": "user"}, headers=deputy_auth
        )
    ).status_code == 200

    # Now the deputy is alone, and cannot demote the original admin's replacement
    # — there is nobody left to demote except themselves, which is also blocked.
    resp = await client.patch(
        f"/api/v1/admin/users/{deputy_id}", json={"role": "user"}, headers=deputy_auth
    )
    assert resp.status_code == 403  # self_role_change catches it first


async def test_an_admin_cannot_suspend_themselves(admin_client: AsyncClient) -> None:
    me = await _user_id(admin_client)
    resp = await admin_client.patch(f"/api/v1/admin/users/{me}", json={"suspended": True})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "self_suspend"


async def test_an_admin_cannot_delete_themselves(admin_client: AsyncClient) -> None:
    me = await _user_id(admin_client)
    resp = await admin_client.delete(f"/api/v1/admin/users/{me}")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "self_delete"


async def test_deleting_the_last_admin_is_refused(
    admin_client: AsyncClient, client: AsyncClient
) -> None:
    second = await client.post(
        "/api/v1/auth/register",
        json={"username": "deputy", "password": "pw12345678", "display_name": "Deputy"},
    )
    deputy_id = second.json()["user"]["id"]
    await admin_client.patch(f"/api/v1/admin/users/{deputy_id}", json={"role": "admin"})
    admin_id = await _user_id(admin_client)

    # Deputy demotes the first admin, leaving themselves alone...
    deputy_auth = {"Authorization": f"Bearer {second.json()['token']}"}
    await client.patch(
        f"/api/v1/admin/users/{admin_id}", json={"role": "user"}, headers=deputy_auth
    )
    # ...and the (now ordinary) first account cannot delete the last admin,
    # because it is no longer an admin at all.
    assert (await admin_client.delete(f"/api/v1/admin/users/{deputy_id}")).status_code == 403


# --- suspension -------------------------------------------------------------


async def test_a_suspended_user_cannot_log_in_or_use_their_token(
    admin_client: AsyncClient, other_client: AsyncClient, client: AsyncClient
) -> None:
    """Two halves, both needed.

    Tokens are stateless and last a week, so checking only at login would leave a
    suspended account fully working until the token expired.
    """
    learner = await _find(admin_client, "other")
    resp = await admin_client.patch(
        f"/api/v1/admin/users/{learner['id']}",
        json={"suspended": True, "suspended_reason": "Repeated abuse"},
    )
    assert resp.status_code == 200
    assert resp.json()["suspended_at"] is not None

    # The token they already hold stops working immediately.
    blocked = await other_client.get("/api/v1/users/me")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "account_suspended"

    # And a fresh login is refused with a reason, not "wrong password".
    login = await client.post(
        "/api/v1/auth/login", json={"username": "other", "password": "pw12345678"}
    )
    assert login.status_code == 403
    assert login.json()["error"]["code"] == "account_suspended"
    assert "Repeated abuse" in login.json()["error"]["message"]


async def test_lifting_a_suspension_restores_access(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    learner = await _find(admin_client, "other")
    await admin_client.patch(f"/api/v1/admin/users/{learner['id']}", json={"suspended": True})
    assert (await other_client.get("/api/v1/users/me")).status_code == 403

    lifted = await admin_client.patch(
        f"/api/v1/admin/users/{learner['id']}", json={"suspended": False}
    )
    assert lifted.json()["suspended_at"] is None
    assert (await other_client.get("/api/v1/users/me")).status_code == 200


# --- listing ----------------------------------------------------------------


async def test_search_matches_username_or_display_name(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    by_username = await admin_client.get("/api/v1/admin/users", params={"q": "oth"})
    by_name = await admin_client.get("/api/v1/admin/users", params={"q": "OTHER"})
    assert [u["username"] for u in by_username.json()["items"]] == ["other"]
    # Case-insensitive, and matches the display name too.
    assert [u["username"] for u in by_name.json()["items"]] == ["other"]


async def test_the_total_uses_the_same_filters_as_the_rows(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """A total computed with different filters than the rows is a pager that lies."""
    page = await admin_client.get("/api/v1/admin/users", params={"role": "admin"})
    body = page.json()
    assert body["total"] == len(body["items"]) == 1
    assert body["items"][0]["username"] == "admin"


async def test_a_row_carries_the_numbers_that_make_it_actionable(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    room = (await other_client.post("/api/v1/match/random", json={"mode": "normal"})).json()
    await other_client.post(f"/api/v1/rooms/{room['id']}/join", json={})
    await other_client.post(f"/api/v1/rooms/{room['id']}/messages", json={"text": "hello"})

    learner = await _find(admin_client, "other")
    assert learner["messages_sent"] == 1
    assert learner["reports_against"] == 0
    assert learner["role"] == "user"


async def test_plan_can_be_changed_by_an_admin(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    learner = await _find(admin_client, "other")
    resp = await admin_client.patch(
        f"/api/v1/admin/users/{learner['id']}", json={"plan": "premium"}
    )
    assert resp.status_code == 200
    assert resp.json()["plan"] == "premium"
    assert (await other_client.get("/api/v1/users/me")).json()["plan"] == "premium"


async def test_unknown_user_is_404(admin_client: AsyncClient) -> None:
    assert (
        await admin_client.patch(f"/api/v1/admin/users/{uuid.uuid4()}", json={"plan": "free"})
    ).status_code == 404


# --- audit ------------------------------------------------------------------


async def test_every_write_is_recorded(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    learner = await _find(admin_client, "other")
    await admin_client.patch(f"/api/v1/admin/users/{learner['id']}", json={"plan": "premium"})

    entries = (await admin_client.get("/api/v1/admin/audit")).json()
    assert entries, "the plan change should have been logged"
    latest = entries[0]
    assert latest["action"] == "user.update"
    assert latest["actor_name"] == "Admin"
    assert latest["target_name"] == "other"
    assert "plan free -> premium" in latest["detail"]


async def test_a_no_op_update_is_not_logged(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """Setting a field to the value it already has changed nothing, so it is not
    an action. A log full of non-events is a log nobody reads."""
    learner = await _find(admin_client, "other")
    await admin_client.patch(f"/api/v1/admin/users/{learner['id']}", json={"plan": "free"})
    assert (await admin_client.get("/api/v1/admin/audit")).json() == []


# --- overview ---------------------------------------------------------------


async def test_overview_counts(admin_client: AsyncClient, other_client: AsyncClient) -> None:
    body = (await admin_client.get("/api/v1/admin/overview")).json()
    assert body["total_users"] == 2
    assert body["admins"] == 1
    assert body["suspended"] == 0
    assert body["open_reports"] == 0
    assert body["active_bans"] == 0


async def test_ai_spend_is_empty_but_well_formed_with_no_usage(
    admin_client: AsyncClient,
) -> None:
    body = (await admin_client.get("/api/v1/admin/ai-spend")).json()
    assert body["today_usd"] == "0.000000"
    assert body["by_task"] == []
    assert body["failed_24h"] == 0


async def test_ai_spend_attributes_cost_to_a_real_user(
    admin_client: AsyncClient, other_client: AsyncClient
) -> None:
    """The empty case was covered; the case with data was not.

    This is the whole point of the page — a vendor dashboard gives one total and
    cannot say which feature ate the budget or what one learner costs.
    """
    import uuid as _uuid
    from decimal import Decimal

    from app.db.session import AsyncSessionLocal
    from app.models.ai_usage import AiUsage

    learner = await _find(admin_client, "other")

    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                AiUsage(
                    user_id=_uuid.UUID(learner["id"]),
                    task="rescue",
                    provider="openai",
                    model="gpt-4o-mini",
                    cost_usd=Decimal("0.000011"),
                    ok=True,
                ),
                AiUsage(
                    user_id=_uuid.UUID(learner["id"]),
                    task="ielts_report",
                    provider="openai",
                    model="gpt-5-mini",
                    cost_usd=Decimal("0.020000"),
                    ok=True,
                ),
                # A failure is recorded too: an outage should be visible in the
                # data, not only in a log nobody reads.
                AiUsage(
                    task="translation",
                    provider="openai",
                    model="gpt-4o-mini",
                    cost_usd=Decimal("0"),
                    ok=False,
                    degraded=True,
                ),
            ]
        )
        await session.commit()

    body = (await admin_client.get("/api/v1/admin/ai-spend")).json()

    assert Decimal(body["today_usd"]) == Decimal("0.020011")
    # Money is a decimal STRING on the wire, never a float: this is a bill.
    assert isinstance(body["today_usd"], str)

    tasks = {t["task"]: t for t in body["by_task"]}
    assert Decimal(tasks["ielts_report"]["cost_usd"]) == Decimal("0.020000")
    assert tasks["rescue"]["calls"] == 1
    # Sorted most expensive first — that is the one worth looking at.
    assert body["by_task"][0]["task"] == "ielts_report"

    assert len(body["by_user"]) == 1
    assert body["by_user"][0]["username"] == "other"
    assert Decimal(body["by_user"][0]["cost_usd"]) == Decimal("0.020011")

    assert body["failed_24h"] == 1
    health = {h["model"]: h for h in body["health"]}
    assert health["gpt-4o-mini"]["failed"] == 1
    assert health["gpt-4o-mini"]["degraded"] == 1


async def test_the_overview_surfaces_content_gaps(admin_client: AsyncClient) -> None:
    """A topic with no questions looks fine in the topic list and is empty in the
    room. This number is what turns a hunt into a to-do list."""
    await admin_client.post(
        "/api/v1/topics", json={"slug": "empty-topic", "title": "Empty topic"}
    )
    body = (await admin_client.get("/api/v1/admin/overview")).json()
    assert body["topics_without_questions"] == 1
