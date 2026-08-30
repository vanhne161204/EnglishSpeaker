"""Band calibration gate for the IELTS report (docs/10_AI_Design.md §10.8).

Answers the question the unit tests cannot: **are the bands right?**

    cd backend
    .venv/Scripts/python.exe scripts/run_band_eval.py
    .venv/Scripts/python.exe scripts/run_band_eval.py openai:gpt-5-mini

Three metrics, and the second is the one that decides shipping:

    MAE            mean absolute error ............ target <= 0.5 band
    SIGNED ERROR   mean signed error .............. target within +/-0.25
    SPREAD         std dev of predictions ......... target >= 0.8

**Mean absolute error hides inflation.** A model that reads every transcript half
a band high scores 0.5 MAE and looks acceptable, while every learner is being
lied to. The *signed* error is what exposes it: a systematic +0.7 means the model
is generous, and no amount of "be strict" in the prompt fixes that — re-anchor
with the examples in §10.3.13 instead.

**Spread** catches the other failure: a model that answers 6.5 for everything
scores well on a set centred near 6.5 and is completely useless.

This spends real money — roughly $0.30 on gpt-5-mini for the full set. Run it
before a routing change, not in CI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.errors import ProviderError, ProviderRateLimited  # noqa: E402
from app.ai.registry import get_provider  # noqa: E402
from app.ai.routing import AiTask, get_route  # noqa: E402
from app.models.enums import PlanTier  # noqa: E402
from app.models.session_report import SessionReport  # noqa: E402
from app.models.transcript import TranscriptSegment  # noqa: E402
from app.services.ielts import IeltsService, NotEnoughSpeech, ReportUnavailable  # noqa: E402

GOLD = Path(__file__).resolve().parent.parent / "tests" / "data" / "band_calibration.jsonl"

MAE_TARGET = 0.5
SIGNED_TARGET = 0.25
SPREAD_TARGET = 0.8


class _MemoryRepo:
    """Stands in for the DB — calibration needs no persistence."""

    async def add(self, report: SessionReport) -> SessionReport:
        return report


def load_transcripts(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def to_segments(case: dict) -> tuple[list[TranscriptSegment], uuid.UUID]:
    """Turn a calibration case into segments with realistic timing.

    The `gap` on each turn is what makes the measured metrics meaningful: a
    Band 4 transcript carries long pauses, a Band 8 one does not. Without that
    the fluency evidence would be identical for every case.
    """
    learner, partner = uuid.uuid4(), uuid.uuid4()
    room = uuid.uuid4()
    start = datetime.now(UTC) - timedelta(minutes=10)
    segments: list[TranscriptSegment] = []
    offset = 0.0
    for turn in case["turns"]:
        offset += float(turn.get("gap", 3))
        is_learner = turn["who"] == "learner"
        segments.append(
            TranscriptSegment(
                id=uuid.uuid4(),
                room_id=room,
                user_id=learner if is_learner else partner,
                speaker_name="Learner" if is_learner else "Partner",
                text=turn["text"],
                spoken_at=start + timedelta(seconds=offset),
            )
        )
    return segments, learner


async def score_one(provider, route, case: dict, attempts: int = 3) -> tuple[dict, float | None]:
    """Score one transcript, backing off on rate limits.

    A band report is a large request — 12k output tokens with reasoning — so a
    handful in parallel can trip a tokens-per-minute cap. That is a limit of this
    script, not of the product, and retrying is the right response here: unlike
    the live path, nobody is waiting.
    """
    segments, learner = to_segments(case)
    service = IeltsService(provider, route, _MemoryRepo())  # type: ignore[arg-type]
    for attempt in range(attempts):
        try:
            report = await service.build_report(learner, segments)
            return case, float(Decimal(str(report.band_overall)))
        except NotEnoughSpeech as exc:
            print(f"  {case['id']}: SKIPPED ({exc})")
            return case, None
        except (ReportUnavailable, ProviderRateLimited, ProviderError) as exc:
            if attempt + 1 < attempts:
                await asyncio.sleep(5 * (attempt + 1))
                continue
            print(f"  {case['id']}: FAILED ({type(exc).__name__}: {exc})")
            return case, None
    return case, None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", nargs="?", help='e.g. "openai:gpt-5-mini"')
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    route = get_route(AiTask.ielts_report, PlanTier.premium)
    key = args.model or route.chain[0]
    try:
        provider = get_provider(key)
    except ProviderError as exc:
        print(f"Cannot use {key}: {exc}")
        return 2

    cases = load_transcripts(GOLD)
    if args.limit:
        cases = cases[: args.limit]

    print("=" * 78)
    print(f"IELTS band calibration — {key}")
    print(f"{len(cases)} transcripts from {GOLD.name}")
    print("=" * 78)

    # Low concurrency on purpose. Each report is a ~12k-output-token request, so
    # four at once reliably trips a tokens-per-minute cap.
    semaphore = asyncio.Semaphore(2)

    async def run(case):
        async with semaphore:
            return await score_one(provider, route, case)

    results = await asyncio.gather(*(run(c) for c in cases))

    errors: list[float] = []
    predictions: list[float] = []
    rows: list[tuple[str, float, float, float]] = []
    failed = 0

    for case, predicted in results:
        if predicted is None:
            failed += 1
            continue
        expected = float(case["band"])
        errors.append(predicted - expected)
        predictions.append(predicted)
        rows.append((case["id"], expected, predicted, predicted - expected))

    if not rows:
        print("\nNo transcript could be scored.")
        return 1

    mae = statistics.fmean(abs(e) for e in errors)
    signed = statistics.fmean(errors)
    spread = statistics.pstdev(predictions) if len(predictions) > 1 else 0.0

    print(f"\n{'case':10s} {'expected':>9s} {'predicted':>10s} {'error':>7s}")
    for case_id, expected, predicted, error in sorted(rows, key=lambda r: r[1]):
        flag = "  <-- off by more than a band" if abs(error) > 1.0 else ""
        print(f"{case_id:10s} {expected:9.1f} {predicted:10.1f} {error:+7.1f}{flag}")

    print("\n" + "-" * 78)
    print(f"  MAE ............ {mae:5.2f}   (target <= {MAE_TARGET})")
    print(f"  SIGNED ERROR ... {signed:+5.2f}   (target within +/-{SIGNED_TARGET})")
    print(f"  SPREAD (sd) .... {spread:5.2f}   (target >= {SPREAD_TARGET})")
    if failed:
        print(f"  FAILED ......... {failed} transcript(s) could not be scored")

    mae_ok = mae <= MAE_TARGET
    signed_ok = abs(signed) <= SIGNED_TARGET
    spread_ok = spread >= SPREAD_TARGET

    print("-" * 78)
    print(f"  accuracy (MAE)     {'PASS' if mae_ok else 'FAIL'}")
    print(f"  bias   (signed)    {'PASS' if signed_ok else 'FAIL'}")
    print(f"  spread             {'PASS' if spread_ok else 'FAIL'}")

    if mae_ok and signed_ok and spread_ok:
        print(f"\n{key} PASSES. Bands from this model are safe to show learners.")
        print("=" * 78)
        return 0

    print(f"\n{key} FAILS. Do NOT show bands from this model.")
    if not signed_ok:
        direction = "GENEROUS" if signed > 0 else "HARSH"
        print(f"It is systematically {direction} by {abs(signed):.2f} of a band.")
        print("Adding 'be strict' to the prompt barely moves a model — re-anchor")
        print("with scored example transcripts instead (docs §10.3.13, defence 3).")
    if not spread_ok:
        print("Predictions are clustered: the model is guessing a safe middle band")
        print("rather than discriminating between them.")
    print("=" * 78)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
