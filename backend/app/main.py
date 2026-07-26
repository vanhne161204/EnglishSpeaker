"""Application entrypoint and factory."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (registers models on Base.metadata)
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging("DEBUG" if settings.debug else "INFO")
    logger.info("Starting %s (env=%s)", settings.app_name, settings.environment)

    # Fail fast rather than run production with a forgeable, public JWT secret.
    if settings.is_production and settings.secret_key == "change-me-in-production":
        raise RuntimeError(
            "SECRET_KEY is still the insecure default. Set a strong random "
            "SECRET_KEY (e.g. `openssl rand -hex 32`) before running in production."
        )

    # Dev-only bootstrap. Production uses Alembic migrations (see alembic/).
    if settings.auto_create_tables and not settings.is_production:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Demo data is opt-in (SEED_DEMO_DATA=true) so the app normally starts
        # with only real, user-created content.
        if settings.seed_demo_data:
            from app.seeds.demo import seed_demo_data

            await seed_demo_data()

    yield

    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        # Only the configured frontend origins may call the API (set CORS_ORIGINS
        # to your real domain in production). Exact origins — not "*" — so
        # credentialed requests are allowed and unknown sites are rejected.
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
