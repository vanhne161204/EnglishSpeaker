"""Pytest fixtures: fresh schema per test + async HTTP client over the ASGI app.

IMPORTANT: force a dedicated test database *before* importing the app, so running
the suite never touches (and ``drop_all``s!) the dev database the local server uses.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_englishtalker.db")
# Tests manage their own schema; never auto-seed demo data into the test DB.
os.environ.setdefault("AUTO_CREATE_TABLES", "false")

# Force every AI call to the offline stub. A developer with a real key in .env
# would otherwise have the suite hit the live API: slow, flaky, and it spends
# money on every run. Tests that need real model behaviour inject a
# FakeProvider (tests/test_ai_providers.py); the one script that talks to the
# network is scripts/check_ai_provider.py, run by hand.
os.environ["AI_ENABLED"] = "false"

from collections.abc import AsyncGenerator  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core import rate_limit  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _setup_database() -> AsyncGenerator[None, None]:
    # The rate limiter keeps hit counts in a module-level global; clear it so the
    # per-IP throttles (e.g. register: 5/window) don't leak across tests and trip
    # a spurious 429 once several tests have registered from the same client IP.
    rate_limit._hits.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """``client`` authenticated as an admin.

    The role is granted **explicitly**, by writing the column. Registering with
    the username "admin" no longer confers anything — that allowlist is exactly
    what docs/11_Security.md §11.2 removed, and a fixture that relied on it would
    quietly pass even if the behaviour came back.
    """
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "admin", "password": "admin-password", "display_name": "Admin"},
    )
    assert resp.status_code == 200, resp.text

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one()
        user.role = UserRole.admin
        await session.commit()

    # Re-login so the token carries the new role claim (the server re-reads the
    # role from the database on every request either way).
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )
    assert resp.status_code == 200, resp.text
    client.headers["Authorization"] = f"Bearer {resp.json()['token']}"
    yield client


@pytest_asyncio.fixture
async def user_client(client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """``client`` authenticated as an ordinary (non-admin) learner.

    Rooms, notes, transcripts and reports all require an account now
    (docs/11_Security.md §11.2), so most tests need this rather than ``client``.
    Use bare ``client`` only to assert that something is *rejected* without auth.
    """
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "learner", "password": "pw12345678", "display_name": "Learner"},
    )
    assert resp.status_code == 200, resp.text
    client.headers["Authorization"] = f"Bearer {resp.json()['token']}"
    yield client


@pytest_asyncio.fixture
async def other_client() -> AsyncGenerator[AsyncClient, None]:
    """A SECOND authenticated learner, on their own HTTP client.

    Needed to prove isolation: that one learner cannot read, edit or delete
    another's notes, transcripts or reports.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/register",
            json={"username": "other", "password": "pw12345678", "display_name": "Other"},
        )
        assert resp.status_code == 200, resp.text
        ac.headers["Authorization"] = f"Bearer {resp.json()['token']}"
        yield ac
