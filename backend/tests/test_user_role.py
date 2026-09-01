"""Where admin authority comes from (docs/11_Security.md §11.2).

The answer is: the ``users.role`` column, and nothing else.

It used to come from a username. ``ADMIN_USERNAMES`` was an allowlist that was
re-applied on **every login**, which meant two bad things at once — anyone who
registered the configured name got the keys, and any grant or revoke made in the
admin panel was silently undone at that person's next sign-in.

These tests exist to stop that coming back.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, decode_access_token
from app.db.session import AsyncSessionLocal
from app.models.enums import UserRole
from app.models.user import User


async def _role_of(username: str) -> str:
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one()
        return user.role


async def _set_role(username: str, role: UserRole) -> None:
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one()
        user.role = role
        await session.commit()


# --- a name is just a name --------------------------------------------------


async def test_a_new_account_is_always_an_ordinary_user(client: AsyncClient) -> None:
    for username in ("alice", "admin", "administrator", "root"):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": username, "password": "pw12345678"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["user"]["role"] == "user", username


async def test_there_is_no_setting_that_grants_admin_by_name() -> None:
    """A configuration knob that hands out admin is the thing being removed.

    If someone reintroduces one, this fails.
    """
    from app.core.config import settings

    forbidden = [k for k in settings.model_dump() if "admin" in k.lower()]
    assert forbidden == [], f"config still has username-based admin settings: {forbidden}"


async def test_the_client_cannot_ask_to_be_an_admin(client: AsyncClient) -> None:
    """`role` is not in RegisterRequest, so it is ignored rather than rejected —
    the same shape as every other identity field in this API."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "sneaky", "password": "pw12345678", "role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "user"


# --- the column is the authority --------------------------------------------


async def test_promoting_in_the_database_grants_access(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/auth/register", json={"username": "alice", "password": "pw12345678"}
    )
    auth = {"Authorization": f"Bearer {resp.json()['token']}"}
    assert (await client.get("/api/v1/admin/overview", headers=auth)).status_code == 403

    await _set_role("alice", UserRole.admin)

    # The SAME token now works: the role is re-read from the database on every
    # request, so access does not wait for a new login.
    assert (await client.get("/api/v1/admin/overview", headers=auth)).status_code == 200


async def test_revoking_takes_effect_on_the_next_request(admin_client: AsyncClient) -> None:
    """A stale token must not keep admin rights after they are taken away."""
    assert (await admin_client.get("/api/v1/admin/overview")).status_code == 200
    await _set_role("admin", UserRole.user)
    assert (await admin_client.get("/api/v1/admin/overview")).status_code == 403


async def test_the_role_claim_in_the_token_is_not_the_authority(
    client: AsyncClient,
) -> None:
    """The token carries a `role` claim for convenience only.

    Forging one proves nothing, because the server never reads it to decide.
    """
    resp = await client.post(
        "/api/v1/auth/register", json={"username": "alice", "password": "pw12345678"}
    )
    user_id = resp.json()["user"]["id"]

    # A validly SIGNED token that claims admin, for an account that is not one.
    forged = create_access_token(user_id, "admin")
    assert decode_access_token(forged)["role"] == "admin"

    denied = await client.get(
        "/api/v1/admin/overview", headers={"Authorization": f"Bearer {forged}"}
    )
    assert denied.status_code == 403


async def test_a_token_claiming_admin_for_nobody_is_rejected(client: AsyncClient) -> None:
    forged = create_access_token(uuid.uuid4(), "admin")
    resp = await client.get(
        "/api/v1/admin/overview", headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401


# --- the grant script -------------------------------------------------------


async def test_grant_admin_script_promotes_and_revokes(client: AsyncClient) -> None:
    """`scripts/grant_admin.py` is how the FIRST admin is created, so it has to
    work — there is no allowlist to fall back on."""
    from scripts.grant_admin import _set_role as script_set_role

    await client.post(
        "/api/v1/auth/register", json={"username": "alice", "password": "pw12345678"}
    )

    assert await script_set_role("alice", UserRole.admin) == 0
    assert await _role_of("alice") == "admin"

    # A second admin, so the next demotion is allowed.
    await client.post(
        "/api/v1/auth/register", json={"username": "bob", "password": "pw12345678"}
    )
    assert await script_set_role("bob", UserRole.admin) == 0

    assert await script_set_role("alice", UserRole.user) == 0
    assert await _role_of("alice") == "user"


async def test_grant_admin_script_refuses_to_remove_the_last_admin(
    client: AsyncClient,
) -> None:
    """Otherwise the recovery tool becomes the way to lock everyone out."""
    from scripts.grant_admin import _set_role as script_set_role

    await client.post(
        "/api/v1/auth/register", json={"username": "alice", "password": "pw12345678"}
    )
    await script_set_role("alice", UserRole.admin)

    assert await script_set_role("alice", UserRole.user) == 1  # non-zero exit
    assert await _role_of("alice") == "admin"


async def test_grant_admin_script_reports_an_unknown_username() -> None:
    from scripts.grant_admin import _set_role as script_set_role

    assert await script_set_role("nobody", UserRole.admin) == 1
