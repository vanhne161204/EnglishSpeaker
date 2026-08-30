"""Smoke-test the AI provider layer against the real API.

Verifies the wiring end to end — key, SDK, model id, structured output, cost
accounting — and prints what one call actually costs. Run it after adding a key
to `.env`, before wiring any feature to a new model.

    cd backend
    .venv/Scripts/python.exe scripts/check_ai_provider.py

    # or pin one model, ignoring the routing table:
    .venv/Scripts/python.exe scripts/check_ai_provider.py openai:gpt-5-nano

This spends real money — roughly $0.00002 on gpt-5-nano. That is two thousandths
of a cent, but it is not zero, so it is a script you run, not a test in CI.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Run from anywhere: put `backend/` on the path before importing `app`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel  # noqa: E402

from app.ai.errors import ProviderError  # noqa: E402
from app.ai.ports import Effort, LLMRequest  # noqa: E402
from app.ai.registry import build_chain  # noqa: E402
from app.ai.routing import AiTask, get_route  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models.enums import PlanTier  # noqa: E402


class Correction(BaseModel):
    """Deliberately shaped like the real layer-1 schema (docs/10_AI_Design §10.3.5)."""

    is_correct: bool
    corrected: str | None
    natural: str


async def main() -> int:
    keys = [sys.argv[1]] if len(sys.argv) > 1 else None
    # Exercise the LIVE rescue route by default, so this tests what production
    # actually runs rather than a separate list that could drift from it.
    route = get_route(AiTask.rescue, PlanTier.free)

    print("=" * 68)
    print("AI provider check")
    print("=" * 68)
    print(f"  AI_ENABLED    : {settings.ai_enabled}")
    print(f"  route chain   : {keys or list(route.chain)}")
    print(f"  OPENAI key    : {'set' if settings.openai_api_key else 'NOT SET'}")
    print(f"  ANTHROPIC key : {'set' if settings.anthropic_api_key else 'NOT SET'}")

    chain = build_chain(keys or list(route.chain))
    print(f"  resolved to   : {chain.name}\n")

    total = Decimal(0)

    # --- 1. plain text ----------------------------------------------------
    print("[1/2] plain text ...")
    try:
        response = await chain.generate(
            LLMRequest(
                system=(
                    "You are an English coach. Reply with ONE short sentence a "
                    "learner could say next. No quotes, no explanation."
                ),
                user="My partner just asked: 'What did you do last weekend?'",
                max_tokens=100,
                timeout_s=30.0,
                effort=Effort.low,
            )
        )
    except ProviderError as exc:
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        return 1

    total += response.cost_usd
    _report(response)

    if response.provider == "stub":
        print("\n  Running on the STUB — no API key was usable.")
        print("  Add OPENAI_API_KEY to backend/.env and run again.")
        return 1

    # --- 2. structured output ---------------------------------------------
    print("\n[2/2] structured output ...")
    try:
        structured = await chain.generate(
            LLMRequest(
                system=(
                    "You are an English coach reviewing SPOKEN English. Ignore "
                    "punctuation and capitals. Return the correction."
                ),
                user="I go to Da Nang yesterday with my family.",
                max_tokens=500,
                timeout_s=30.0,
                effort=Effort.low,
                schema=Correction,
            )
        )
    except ProviderError as exc:
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        return 1

    total += structured.cost_usd
    _report(structured)

    if structured.parsed is None:
        print("  WARNING: no parsed object came back — structured output is not working.")
        return 1

    parsed: Correction = structured.parsed  # type: ignore[assignment]
    print(f"    is_correct : {parsed.is_correct}")
    print(f"    corrected  : {parsed.corrected}")
    print(f"    natural    : {parsed.natural}")

    print("\n" + "=" * 68)
    print(f"OK. Total spend this run: ${total:.8f}")
    # docs/10_AI_Design.md §10.9 budgets ~60 sentences per practice session.
    print(f"At this rate, 60 sentences would cost about ${total / 2 * 60:.5f}")
    print("=" * 68)
    return 0


def _report(response) -> None:
    print(f"  model    : {response.model}  ({response.provider})")
    print(f"  degraded : {response.degraded}")
    print(f"  latency  : {response.latency_ms} ms")
    print(
        f"  tokens   : {response.usage.input_tokens} in "
        f"/ {response.usage.output_tokens} out "
        f"/ {response.usage.cached_input_tokens} cached"
    )
    print(f"  cost     : ${response.cost_usd:.8f}")
    if response.text:
        print(f"  text     : {response.text[:160]}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
