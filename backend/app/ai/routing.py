"""Which model runs which task, for which plan tier (docs §18.5).

The adapters make providers *swappable*; this table is what actually *switches*
them. Defaults live here so the app runs out of the box; ``AI_ROUTES`` overrides
any entry from the environment, so changing a model is a container restart rather
than a release.

Timeouts and token budgets are per task, not global. A live coach that must
answer inside three seconds and a batch IELTS report that may take two minutes
have nothing in common except the port they call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum

from app.ai.ports import Effort
from app.core.config import settings
from app.models.enums import PlanTier

logger = logging.getLogger(__name__)


class AiTask(StrEnum):
    """Every distinct AI job in the product. One row per task in the table below."""

    #: In-room "I'm stuck" coach (docs/10_AI_Design.md §10.2). Latency-critical.
    rescue = "rescue"
    #: In-room translator, when backed by an LLM rather than Google/Argos.
    translate = "translate"
    #: Coach Report layer 1 — per-sentence grammar/vocab (§10.3.1).
    sentence_check = "sentence_check"
    #: Coach Report layer 2 — the IELTS band report (§10.3.7).
    ielts_report = "ielts_report"


@dataclass(frozen=True, slots=True)
class Route:
    chain: tuple[str, ...]
    effort: Effort
    max_tokens: int
    timeout_s: float
    cache_system: bool = False


# Measured against the live API on 2026-08-29 (scripts/check_ai_provider.py):
#
#   gpt-4o-mini   median 1314 ms, max 1991 ms, $0.000011/call
#   gpt-5-nano    median 1752 ms, max 5660 ms, $0.000052/call
#
# Two findings drive the choices below.
#
# 1. gpt-4o-mini is ~5x CHEAPER per short call than gpt-5-nano despite a 3x
#    higher list price. gpt-5-nano is a reasoning model and bills 100-200
#    invisible thinking tokens as output to write one sentence. For short
#    answers the headline price is misleading.
# 2. gpt-5-nano's latency is volatile (1.75s-5.7s observed). A 2s ceiling on the
#    rescue path would drop a large share of calls to the stub.
#
# So: a non-reasoning model on the live path, reasoning models for batch work
# where thinking earns its cost and nobody is waiting.
_RESCUE_TIMEOUT_S = 3.0

DEFAULT_ROUTES: dict[tuple[AiTask, PlanTier], Route] = {
    # --- Live path: fast, cheap, no retry (a retry doubles the wait in a call) ---
    (AiTask.rescue, PlanTier.free): Route(
        chain=("openai:gpt-4o-mini", "anthropic:claude-haiku-4-5"),
        effort=Effort.low,
        max_tokens=400,
        timeout_s=_RESCUE_TIMEOUT_S,
    ),
    (AiTask.rescue, PlanTier.premium): Route(
        chain=("anthropic:claude-haiku-4-5", "openai:gpt-4o-mini"),
        effort=Effort.low,
        max_tokens=400,
        timeout_s=_RESCUE_TIMEOUT_S,
    ),
    # --- Translator (only used when TRANSLATION_PROVIDER routes to an LLM) ---
    (AiTask.translate, PlanTier.free): Route(
        chain=("openai:gpt-4o-mini", "anthropic:claude-haiku-4-5"),
        effort=Effort.low,
        max_tokens=1024,
        timeout_s=10.0,
    ),
    (AiTask.translate, PlanTier.premium): Route(
        chain=("openai:gpt-4o-mini", "anthropic:claude-haiku-4-5"),
        effort=Effort.low,
        max_tokens=1024,
        timeout_s=10.0,
    ),
    # --- Batch: quality over latency ---
    #
    # Model choice here is gated on scripts/run_feedback_eval.py, not on price.
    # Measured 2026-08-29 against tests/data/feedback_gold.jsonl (50 cases):
    #
    #   openai:gpt-5-mini    recall 100%  false positives  0/30   PASS
    #   openai:gpt-4o-mini   recall  PASS  false positives 11/30   FAIL
    #
    # gpt-4o-mini "corrected" 7 of the 10 garbled speech-to-text lines — it
    # rewrote "I went to the the the market" as a grammar fix. Real transcripts
    # are full of those, so it would flag a learner's every stutter as a mistake.
    # It is fine for `rescue` (suggesting what to say is not judging grammar) and
    # must never be routed here. Re-run the eval before changing these.
    (AiTask.sentence_check, PlanTier.free): Route(
        chain=("openai:gpt-5-mini", "anthropic:claude-sonnet-5"),
        effort=Effort.medium,
        max_tokens=8000,
        timeout_s=90.0,
    ),
    (AiTask.sentence_check, PlanTier.premium): Route(
        # Ends with an OpenAI model on purpose. An all-Anthropic chain leaves a
        # PAYING learner on the stub whenever ANTHROPIC_API_KEY is unset, which
        # is worse than what the free tier gets. gpt-5-mini earns its place here:
        # 100% recall / 0% false positives on the gold set.
        chain=("anthropic:claude-opus-5", "anthropic:claude-sonnet-5", "openai:gpt-5-mini"),
        effort=Effort.medium,
        max_tokens=8000,
        timeout_s=90.0,
    ),
    # The band report is a judgement call — the one place high effort pays off.
    (AiTask.ielts_report, PlanTier.free): Route(
        chain=("anthropic:claude-sonnet-5", "openai:gpt-5-mini"),
        effort=Effort.medium,
        max_tokens=8000,
        timeout_s=120.0,
        cache_system=True,
    ),
    (AiTask.ielts_report, PlanTier.premium): Route(
        chain=("anthropic:claude-opus-5", "anthropic:claude-sonnet-5", "openai:gpt-5-mini"),
        effort=Effort.high,
        max_tokens=8000,
        timeout_s=120.0,
        cache_system=True,
    ),
}


def _overrides() -> dict[tuple[AiTask, PlanTier], Route]:
    """Parse ``AI_ROUTES``: {"rescue:free": {"chain": [...], "timeout_s": 3.0}, ...}.

    Partial — only the fields given replace the default, so pinning one model does
    not mean restating a whole Route. A malformed entry is logged and skipped
    rather than crashing the app: a typo in an env var must not stop the API.
    """
    raw = (settings.ai_routes or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("AI_ROUTES is not valid JSON, ignoring it: %s", exc)
        return {}

    out: dict[tuple[AiTask, PlanTier], Route] = {}
    for key, patch in parsed.items():
        try:
            task_name, _, tier_name = key.partition(":")
            slot = (AiTask(task_name), PlanTier(tier_name))
            base = DEFAULT_ROUTES[slot]
            out[slot] = Route(
                chain=tuple(patch.get("chain", base.chain)),
                effort=Effort(patch.get("effort", base.effort.value)),
                max_tokens=int(patch.get("max_tokens", base.max_tokens)),
                timeout_s=float(patch.get("timeout_s", base.timeout_s)),
                cache_system=bool(patch.get("cache_system", base.cache_system)),
            )
        except (ValueError, KeyError, TypeError) as exc:
            logger.error("AI_ROUTES entry %r is invalid, ignoring it: %s", key, exc)
    return out


def get_route(task: AiTask, tier: PlanTier) -> Route:
    """The route for one task and tier, with any ``AI_ROUTES`` override applied."""
    override = _overrides().get((task, tier))
    if override is not None:
        return override
    return DEFAULT_ROUTES[(task, tier)]
