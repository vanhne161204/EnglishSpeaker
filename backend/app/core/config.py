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

    # How long an owner's kick keeps someone out of that room. 0 = permanent.
    # A kick is a time-out from one conversation, not a life sentence, so this
    # defaults to a day rather than forever (docs/11_Security.md Step 4).
    room_ban_hours: int = 24

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

    # --- AI provider layer (docs/18_AI_Provider_Architecture.md) ---
    # Master switch. Set false to force every AI task to the labelled stub — the
    # app keeps working (rooms, voice, chat) and only the AI extras go quiet.
    # This is the incident kill switch; you want it to exist before you need it.
    ai_enabled: bool = True

    # API keys. Set EITHER of these and the app uses it; set neither and
    # everything degrades to a clearly-labelled demo stub.
    #   OpenAI:    https://platform.openai.com/api-keys      (sk-proj-...)
    #   Anthropic: https://console.anthropic.com/settings/keys (sk-ant-...)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Which model runs which task, for which plan tier. This is the ONE place
    # models are chosen — defaults live in app/ai/routing.py, and this patches
    # individual entries without a deploy. Only the fields you name are replaced:
    #   AI_ROUTES='{"rescue:free":{"chain":["openai:gpt-4o-mini"],"timeout_s":3.0}}'
    #
    # Measured 2026-08-29: gpt-4o-mini is ~5x CHEAPER per short call than
    # gpt-5-nano despite a 3x higher list price — gpt-5-nano is a reasoning model
    # and bills ~150 invisible thinking tokens to write one sentence. It is also
    # slower and far more variable (1.75s-5.7s vs 1.3s).
    ai_routes: str | None = None

    # Org-wide 30-day spend ceiling in USD. AI is refused above it, and a warning
    # is logged at 70%. 0 disables the cap — do NOT ship with 0: a looping bug
    # should cost you an alert, not a month of runway (docs §18.9).
    ai_monthly_budget_usd: float = 50.0

    # Legacy. `assist_model` is now unused — AssistantService goes through the
    # provider layer. `translation_model` is still read by the not-yet-migrated
    # TranslationService (docs §18.11, step 5).
    translation_model: str = "claude-haiku-4-5"

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
    # "deepgram" uses the Deepgram cloud API (accurate, no server load; needs a key);
    # "whisper" uses offline faster-whisper (open-source, no LLM); "stub" returns a
    # labelled placeholder so the demo runs with zero setup.
    stt_provider: str = "whisper"
    # faster-whisper model size (tiny | base | small | medium | large-v3).
    stt_model: str = "base"
    # Deepgram API key (only used when stt_provider="deepgram"). Get a free one at
    # deepgram.com. Keep it in .env.prod, never in the repo.
    deepgram_api_key: str | None = None
    # Deepgram model — nova-2 is accurate and cheap; "nova-2-general" also works.
    deepgram_model: str = "nova-2"

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
