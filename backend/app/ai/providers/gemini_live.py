"""Gemini Live adapter: mints ephemeral tokens (PRD §8.12, docs §18.13).

Uses ``client.aio.auth_tokens.create``. The whole session config goes into
``live_connect_constraints``, and ``lock_additional_fields`` is left unset. The
SDK sends that as a *global* lock: the browser cannot change the model, the coach
instructions or anything else. It can only connect with what we minted.
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from app.ai.errors import (
    ProviderBadRequest,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.ai.live_port import LiveToken, LiveTokenMinter, LiveTokenRequest
from app.core.config import settings

logger = logging.getLogger(__name__)

# The SDK warns on every token that the feature is experimental. Once is enough:
# it is documented in docs §18.13, and a warning per session only buries real logs.
warnings.filterwarnings("ignore", message=r".*token creation implementation is experimental.*")

#: How long the browser has to open the session after it gets the token. The
#: token is one-use, so a leaked copy is worthless once the session is open.
NEW_SESSION_WINDOW = timedelta(seconds=60)
MINT_TIMEOUT_S = 10.0


class GeminiLiveTokenMinter:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise ProviderNotConfigured("gemini", "google-genai is not installed") from exc
        self.model = model
        self._client = genai.Client(api_key=api_key)

    async def mint(self, request: LiveTokenRequest) -> LiveToken:
        from google.genai import errors, types

        now = datetime.now(UTC)
        config = types.CreateAuthTokenConfig(
            uses=1,
            expire_time=request.expires_at,
            new_session_expire_time=min(now + NEW_SESSION_WINDOW, request.expires_at),
            live_connect_constraints=types.LiveConnectConstraints(
                model=self.model,
                config=types.LiveConnectConfig(
                    # Native-audio Live models only answer in audio. The captions
                    # come from the two transcription streams below.
                    response_modalities=[types.Modality.AUDIO],
                    system_instruction=request.system_instruction,
                    input_audio_transcription=types.AudioTranscriptionConfig(),
                    output_audio_transcription=types.AudioTranscriptionConfig(),
                ),
            ),
        )
        try:
            token = await asyncio.wait_for(
                self._client.aio.auth_tokens.create(config=config), timeout=MINT_TIMEOUT_S
            )
        except TimeoutError as exc:
            raise ProviderTimeout("gemini", "token request timed out") from exc
        except errors.APIError as exc:
            raise translate_error(exc) from exc
        except Exception as exc:  # noqa: BLE001 — connection errors from the HTTP client
            raise ProviderUnavailable("gemini", str(exc)) from exc
        if not token.name:
            raise ProviderUnavailable("gemini", "no token in the response")
        return LiveToken(token=token.name, model=self.model, provider=self.name)


def translate_error(exc: Any) -> ProviderError:
    code = int(getattr(exc, "code", 0) or 0)
    if code == 429:
        return ProviderRateLimited("gemini")
    if code >= 500:
        return ProviderUnavailable("gemini", str(exc))
    return ProviderBadRequest("gemini", str(exc))


@lru_cache(maxsize=4)
def _minter_for(api_key: str, model: str) -> GeminiLiveTokenMinter:
    # One client per key and model, reused across requests: building a client
    # sets up HTTP connection pools, which is wasted work on every start.
    return GeminiLiveTokenMinter(api_key, model)


def build_live_minter() -> LiveTokenMinter | None:
    """The configured minter, or None when the voice coach is switched off.

    Off when ``AI_ENABLED`` is false (the kill switch, and the test suite) or
    when no ``GEMINI_API_KEY`` is set.
    """
    if not settings.ai_enabled or not settings.gemini_api_key:
        return None
    try:
        return _minter_for(settings.gemini_api_key, settings.gemini_live_model)
    except ProviderNotConfigured:
        logger.warning("GEMINI_API_KEY is set but google-genai is not installed — voice coach off.")
        return None
