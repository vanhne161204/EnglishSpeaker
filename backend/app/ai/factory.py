"""Build the provider stack for one task (docs §18.6).

The single entry point services use. Everything below it — which models, in what
order, with what caps and what recording — is configuration, not code.
"""

from __future__ import annotations

import logging
import uuid

from app.ai.chain import FallbackChain
from app.ai.errors import ProviderError
from app.ai.metering import (
    BudgetGuard,
    MeteredProvider,
    MeteredTranscriber,
    MeteredTranslator,
    UsageSink,
)
from app.ai.ports import LLMProvider
from app.ai.providers.stub import StubProvider
from app.ai.registry import get_provider
from app.ai.routing import AiTask, Route, get_route
from app.ai.stt_port import Transcriber, TranscriberChain
from app.ai.translate_port import Translator, TranslatorChain
from app.core.config import settings
from app.models.enums import PlanTier

logger = logging.getLogger(__name__)


def build_llm(
    task: AiTask,
    tier: PlanTier = PlanTier.free,
    user_id: uuid.UUID | None = None,
    room_id: uuid.UUID | None = None,
    sink: UsageSink | None = None,
) -> tuple[LLMProvider, Route]:
    """Return the provider stack for ``task``, and the route it was built from.

    The route comes back too because it carries the token budget, timeout and
    effort the caller must put into its ``LLMRequest`` — those are per-task
    policy, and a service should not invent its own.

    Composition, outside-in: check the budget -> record the cost -> try each
    provider -> fall back to the stub. A live room never dies because the AI is
    unavailable; it just says so.
    """
    route = get_route(task, tier)

    if not settings.ai_enabled:
        return StubProvider(), route

    providers: list[LLMProvider] = []
    for key in route.chain:
        try:
            providers.append(get_provider(key))
        except ProviderError as exc:
            logger.warning("AI provider %s unavailable for %s, skipping: %s", key, task, exc)

    if not providers:
        logger.warning(
            "No provider configured for task=%s tier=%s (chain: %s) — using the stub. "
            "Set OPENAI_API_KEY or ANTHROPIC_API_KEY.",
            task,
            tier,
            ", ".join(route.chain),
        )

    providers.append(StubProvider())

    stack: LLMProvider = FallbackChain(providers)
    stack = MeteredProvider(stack, sink or UsageSink(), task, user_id, room_id)
    stack = BudgetGuard(stack, task, tier, user_id)
    return stack, route


def build_translator(
    user_id: uuid.UUID | None = None, sink: UsageSink | None = None
) -> Translator:
    """Translator chain from ``TRANSLATION_PROVIDER`` (docs §18.10).

    Order is configuration, not code — the old service hardcoded
    ``if provider in ("google", "auto")`` chains inside its own methods.
    "auto" tries everything good before giving up; a named provider tries just
    that one. Either way the stub is last, so the translator never fails outright.
    """
    from app.ai.providers.translators import (
        ArgosTranslator,
        GoogleTranslator,
        LLMTranslator,
        StubTranslator,
    )

    choice = (settings.translation_provider or "auto").lower()
    engines: list[Translator] = []

    def add_google() -> None:
        engines.append(GoogleTranslator(settings.google_translate_api_key))

    def add_argos() -> None:
        engines.append(ArgosTranslator(settings.argos_auto_download))

    def add_llm() -> None:
        # Reuses the metered, budget-capped LLM stack, so translation spend lands
        # in ai_usage with the rest.
        llm, route = build_llm(AiTask.translation, PlanTier.free, user_id)
        engines.append(LLMTranslator(llm, route.max_tokens, route.timeout_s))

    if choice == "google":
        add_google()
    elif choice == "argos":
        add_argos()
    elif choice in ("claude", "llm", "openai"):
        add_llm()
    elif choice != "stub":  # "auto" and anything unrecognised
        add_google()
        add_argos()
        add_llm()

    engines.append(StubTranslator())

    # Wrapped OUTSIDE the chain, so a fallback's cost is counted and only one row
    # is written per request rather than one per engine tried.
    #
    # The LLM engine is already metered from the inside (it comes from
    # `build_llm`), which would double-count it — but only if it actually
    # answers, and the outer row then carries provider="llm" with $0. Accepted:
    # the alternative is threading a "do not meter me" flag through the chain.
    return MeteredTranslator(TranslatorChain(engines), sink or UsageSink(), user_id)


def build_transcriber(
    user_id: uuid.UUID | None = None, sink: UsageSink | None = None
) -> Transcriber:
    """Speech-to-text chain from ``STT_PROVIDER`` (docs §18.10).

    Metered because Deepgram bills per audio minute. It is $0 today — the
    browser does the work and never reaches this code — but an unmetered paid
    path is a bill you find out about from your card statement.
    """
    from app.ai.providers.transcribers import (
        DeepgramTranscriber,
        FasterWhisperTranscriber,
        StubTranscriber,
    )

    choice = (settings.stt_provider or "auto").lower()
    engines: list[Transcriber] = []

    if choice == "deepgram":
        if settings.deepgram_api_key:
            engines.append(
                DeepgramTranscriber(settings.deepgram_api_key, settings.deepgram_model)
            )
        else:
            logger.warning("STT_PROVIDER=deepgram but DEEPGRAM_API_KEY is not set — skipping.")
    elif choice in ("whisper", "faster_whisper", "auto"):
        engines.append(FasterWhisperTranscriber(settings.stt_model))
        if choice == "auto" and settings.deepgram_api_key:
            engines.append(
                DeepgramTranscriber(settings.deepgram_api_key, settings.deepgram_model)
            )

    engines.append(StubTranscriber())
    return MeteredTranscriber(TranscriberChain(engines), sink or UsageSink(), user_id)
