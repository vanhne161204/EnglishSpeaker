"""Application settings, loaded from environment variables (12-factor)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "EnglishTalker API"
    environment: str = Field(default="development")  # development | staging | production
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # --- Database ---
    # Zero-setup default uses SQLite so the demo runs with no infrastructure.
    # For the real stack, set DATABASE_URL to the Postgres + pgvector instance.
    database_url: str = "sqlite+aiosqlite:///./englishtalker.db"

    # Dev convenience only: auto-create tables on startup.
    # NEVER enable in production — use Alembic migrations instead.
    auto_create_tables: bool = True

    # Insert sample topics/rooms/users on startup (dev demo). Off by default so
    # the app starts with only real, user-created data. Set SEED_DEMO_DATA=true
    # to bring the demo content back.
    seed_demo_data: bool = False

    # Usernames granted admin rights (topic/content management, PRD §9.2). A user
    # becomes admin on register/login if their username is in this list. Override
    # with ADMIN_USERNAMES='["alice","bob"]'.
    admin_usernames: list[str] = ["admin"]

    # --- Redis (matching queues, cache, pub/sub) ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Security / JWT auth ---
    # Secret used to sign session JWTs. MUST be overridden in production with a
    # long random value (e.g. `openssl rand -hex 32`) via SECRET_KEY; if the
    # default is left in production the app refuses to start (see main.py).
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    # Session lifetime. 7 days keeps a practice app from logging users out mid-use;
    # lower it (and add refresh tokens) if you need tighter security.
    access_token_expire_minutes: int = 60 * 24 * 7

    # --- AI / Claude (in-call helpers like the AI coach) ---
    # Leave unset to run the demo with a clearly-labelled stub.
    # Set ANTHROPIC_API_KEY to enable real Claude-powered help.
    anthropic_api_key: str | None = None
    # Haiku is the in-call tier per docs/06_Architecture.md (low latency, low cost).
    translation_model: str = "claude-haiku-4-5"
    # In-room AI coach (sentence improvement / reply ideas) — same in-call tier.
    assist_model: str = "claude-haiku-4-5"

    # --- Translation (in-room translator) ---
    # Engine for the translator (no LLM by default).
    #   "google" — Google Translate; best Vietnamese quality (default)
    #   "argos"  — offline open-source neural MT (no network at translate time)
    #   "claude" — Claude API (needs ANTHROPIC_API_KEY)
    #   "stub"   — labelled demo echo (zero setup)
    #   "auto"   — try google → argos → claude → stub
    translation_provider: str = "google"
    # Official Google Cloud Translation API key. If unset, the "google" provider
    # falls back to the free public endpoint (no key, but unofficial/rate-limited).
    google_translate_api_key: str | None = None
    # Download the needed Argos language model on first use if not already present.
    # In production, prefer pre-installing models at build time (see Dockerfile).
    argos_auto_download: bool = True

    # --- Speech-to-Text (transcription, PRD §8.9) ---
    # "whisper" uses offline faster-whisper (open-source, no LLM); "stub" returns a
    # labelled placeholder so the demo runs without the model installed.
    stt_provider: str = "whisper"
    # faster-whisper model size (tiny | base | small | medium | large-v3).
    stt_model: str = "base"

    # --- CORS ---
    # Exact frontend origins allowed to call the API (credentials-safe — no "*").
    # Override in production with your real domain(s), e.g.
    # CORS_ORIGINS='["https://app.englishtalker.com"]'.
    cors_origins: list[str] = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so settings are parsed once per process."""
    return Settings()


settings = get_settings()
