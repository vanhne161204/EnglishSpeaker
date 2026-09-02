"""Async engine and session management."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug and not settings.is_production,
    future=True,
    pool_pre_ping=True,
)

if engine.dialect.name == "sqlite":
    # SQLite ships with foreign keys DISABLED, per connection, for backwards
    # compatibility with very old databases. Without this pragma every
    # `ondelete="CASCADE"` and `ondelete="SET NULL"` in the schema is silently
    # ignored: deleting a room leaves its messages and transcript behind as
    # orphans pointing at a row that no longer exists.
    #
    # Production is Postgres, which always enforces them. So the real hazard is
    # not SQLite misbehaving in production — it is dev and the test suite
    # behaving DIFFERENTLY from production, which means a cascade can be wrong
    # for months and every test still passes.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a session, commits on success, rolls back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
