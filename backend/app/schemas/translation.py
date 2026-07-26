"""Translation request/response schemas (in-room helper)."""

from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    # ISO-639-1 code of the language to translate into (e.g. "vi", "en").
    target_lang: str = Field(default="vi", min_length=2, max_length=10)
    # Optional hint; the model auto-detects when omitted.
    source_lang: str | None = Field(default=None, max_length=10)


class TranslateResult(BaseModel):
    translated_text: str
    target_lang: str
    # "claude" when powered by the Claude API, "stub" in zero-config demo mode.
    provider: str
