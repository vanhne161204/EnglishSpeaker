"""Pytest fixtures: fresh schema per test + async HTTP client over the ASGI app.

IMPORTANT: force a dedicated test database *before* importing the app, so running
the suite never touches (and ``drop_all``s!) the dev database the local server uses.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_englishtalker.db")
# Tests manage their own schema; never auto-seed demo data into the test DB.
os.environ.setdefault("AUTO_CREATE_TABLES", "false")

from collections.abc import AsyncGenerator  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core import rate_limit  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


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

    The username ``admin`` is in the default ``ADMIN_USERNAMES`` allowlist, so the
    account is granted admin on register — enough to reach the admin-only write
    endpoints (create/update/delete topics and documents).
    """
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "admin", "password": "admin-password", "display_name": "Admin"},
    )
    assert resp.status_code == 200, resp.text
    client.headers["Authorization"] = f"Bearer {resp.json()['token']}"
    yield client
