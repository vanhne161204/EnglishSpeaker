"""IELTS band arithmetic (docs §10.3.9).

Small, but every line here is a bug someone has shipped before.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

#: The realistic range for this product's learners. Values outside it are a
#: model artefact, not a prodigy.
MIN_BAND = Decimal("0")
MAX_BAND = Decimal("9")


def overall_band(*bands: float | Decimal) -> Decimal:
    """Mean of the criteria, rounded to the nearest half band, ``.25`` rounding UP.

    **Do not use Python's ``round()`` here.** It rounds half to even, so
    ``round(6.25 * 2) / 2`` gives ``6.0`` — half a band too low, silently, on
    every report. IELTS rounds ``.25`` up to ``.5`` and ``.75`` up to the next
    whole band.

        >>> overall_band(6.0, 6.5, 6.0, 6.5)   # mean 6.25
        Decimal('6.5')
        >>> overall_band(7.0, 6.5, 7.0, 6.5)   # mean 6.75
        Decimal('7.0')
    """
    if not bands:
        raise ValueError("overall_band needs at least one criterion")
    values = [Decimal(str(b)) for b in bands]
    mean = sum(values) / Decimal(len(values))
    halves = (mean * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return clamp(halves / 2)


def clamp(band: float | Decimal) -> Decimal:
    """Keep a band inside 0-9 and on a half step."""
    value = Decimal(str(band))
    value = max(MIN_BAND, min(MAX_BAND, value))
    return (value * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2


def next_band(band: float | Decimal) -> Decimal:
    """The half band above — what the report's blockers and drills aim at."""
    return clamp(Decimal(str(band)) + Decimal("0.5"))
