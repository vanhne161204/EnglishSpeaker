"""Eval gate for grammar feedback (docs/10_AI_Design.md §10.8).

Answers the question you must answer before shipping Coach Report on any model:
*does it catch real mistakes without inventing fake ones?*

    cd backend
    .venv/Scripts/python.exe scripts/run_feedback_eval.py                      # default route
    .venv/Scripts/python.exe scripts/run_feedback_eval.py openai:gpt-4o-mini   # pin a model

Two metrics, and the second is the one that decides shipping:

    RECALL             real errors caught .................. target > 85%
    FALSE POSITIVE     correct sentences wrongly flagged .... target <  5%

Recall failures waste a lesson. False positives destroy trust AND teach the
learner something false — a learner told their correct sentence is wrong stops
believing the app. That is why the bar is so much tighter on the second one.

The gold set (tests/data/feedback_gold.jsonl) deliberately includes 10 garbled
speech-to-text lines. A model that "corrects" those is unusable here: real
transcripts are full of them.

This spends real money — roughly $0.01 on gpt-4o-mini for the full set. It is a
script you run before a routing change, not a test in CI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field  # noqa: E402

from app.ai.errors import ProviderError  # noqa: E402
from app.ai.ports import LLMRequest  # noqa: E402
from app.ai.registry import get_provider  # noqa: E402
from app.ai.routing import AiTask, get_route  # noqa: E402
from app.models.enums import PlanTier  # noqa: E402

GOLD = Path(__file__).resolve().parent.parent / "tests" / "data" / "feedback_gold.jsonl"

RECALL_TARGET = 0.85
FALSE_POSITIVE_TARGET = 0.05

SYSTEM = """\
You are an English coach reviewing what a learner SAID OUT LOUD in a speaking
practice room. Decide whether each sentence contains a real grammar mistake.

Rules that matter more than anything else:
- This is SPEECH, not writing. Ignore missing punctuation and capitals entirely.
- Do NOT flag contractions, "gonna", fillers, or short answers. People talk like that.
- The speech-to-text may have misheard or duplicated words. A garbled or cut-off
  line is NOT a grammar mistake — mark it correct and move on.
- If the sentence is fine, say it is fine. Do NOT invent a mistake to seem useful.
- Awkward or unnatural is NOT the same as wrong. Only set has_error for real
  grammar mistakes; use `natural` for the smoother version."""


class Verdict(BaseModel):
    has_error: bool
    corrected: str | None = Field(default=None)
    natural: str


@dataclass
class Case:
    id: str
    text: str
    expect_error: bool
    note: str


def load_cases() -> list[Case]:
    with GOLD.open(encoding="utf-8") as fh:
        return [Case(**json.loads(line)) for line in fh if line.strip()]


async def judge(provider, route, case: Case) -> Verdict | None:
    try:
        response = await provider.generate(
            LLMRequest(
                system=SYSTEM,
                user=f"Sentence: {case.text}",
                max_tokens=400,
                timeout_s=60.0,
                effort=route.effort,
                schema=Verdict,
            )
        )
    except ProviderError as exc:
        print(f"  {case.id}: FAILED ({type(exc).__name__}: {exc})")
        return None
    return response.parsed  # type: ignore[return-value]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", nargs="?", help='e.g. "openai:gpt-4o-mini"')
    parser.add_argument("--limit", type=int, default=0, help="run only the first N cases")
    args = parser.parse_args()

    route = get_route(AiTask.sentence_check, PlanTier.premium)
    key = args.model or route.chain[0]
    try:
        provider = get_provider(key)
    except ProviderError as exc:
        print(f"Cannot use {key}: {exc}")
        return 2

    cases = load_cases()
    if args.limit:
        cases = cases[: args.limit]

    print("=" * 74)
    print(f"Grammar feedback eval — {key}")
    print(f"{len(cases)} cases from {GOLD.name}")
    print("=" * 74)

    # Run with bounded concurrency: fast, without tripping a rate limit.
    semaphore = asyncio.Semaphore(5)

    async def run(case: Case):
        async with semaphore:
            return case, await judge(provider, route, case)

    results = await asyncio.gather(*(run(c) for c in cases))

    caught = missed = false_positives = correct_left_alone = errored = 0
    misses: list[Case] = []
    fps: list[tuple[Case, Verdict]] = []

    for case, verdict in results:
        if verdict is None:
            errored += 1
            continue
        if case.expect_error:
            if verdict.has_error:
                caught += 1
            else:
                missed += 1
                misses.append(case)
        else:
            if verdict.has_error:
                false_positives += 1
                fps.append((case, verdict))
            else:
                correct_left_alone += 1

    with_errors = caught + missed
    clean = false_positives + correct_left_alone
    recall = caught / with_errors if with_errors else 0.0
    fp_rate = false_positives / clean if clean else 0.0

    print(
        f"\nRECALL          {caught}/{with_errors} = {recall:6.1%}   "
        f"(target > {RECALL_TARGET:.0%})"
    )
    print(
        f"FALSE POSITIVE  {false_positives}/{clean} = {fp_rate:6.1%}   "
        f"(target < {FALSE_POSITIVE_TARGET:.0%})"
    )
    if errored:
        print(f"ERRORED         {errored} cases could not be judged")

    if misses:
        print(f"\nMISSED real errors ({len(misses)}):")
        for case in misses:
            print(f"  {case.id}  {case.text}")
            print(f"          expected: {case.note}")

    if fps:
        print(f"\nFALSE POSITIVES — correct sentences it called wrong ({len(fps)}):")
        for case, verdict in fps:
            print(f"  {case.id}  {case.text}")
            print(f"          claimed:  {verdict.corrected}")
            print(f"          truth:    {case.note}")

    recall_ok = recall >= RECALL_TARGET
    fp_ok = fp_rate <= FALSE_POSITIVE_TARGET
    print("\n" + "=" * 74)
    print(f"  recall          {'PASS' if recall_ok else 'FAIL'}")
    print(f"  false positive  {'PASS' if fp_ok else 'FAIL'}")
    if recall_ok and fp_ok:
        print(f"\n{key} PASSES. Safe to route learner-facing feedback to it.")
        print("=" * 74)
        return 0
    print(f"\n{key} FAILS. Do NOT ship learner-facing grammar feedback on it.")
    if not fp_ok:
        print("A false positive teaches the learner something FALSE. This is the")
        print("failure mode that loses trust — treat it as blocking, not advisory.")
    print("=" * 74)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
