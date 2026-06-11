"""Nightly skin-temperature rhythm: sustained-shift detection.

A heavily-discussed use of the Sense 2's temperature sensor: spotting
sustained upward shifts in the nightly relative skin temperature. Research on
wrist temperature found surges matching ovulation in ~82% of cycles, and
fevers/illness produce the same signature — so this reports the *pattern*
(when shifts start/end and how big they are) and leaves interpretation to the
wearer. Fitbit's value is already a deviation from your own baseline, so the
detector works on top of a trailing median to be robust to drift and one-off
hot-room nights.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

SHIFT_THRESHOLD = 0.3  # °C above trailing median
MIN_SHIFT_DAYS = 3
BASELINE_WINDOW = 5


@dataclass
class TempShift:
    start: str
    end: str
    days: int
    magnitude: float  # mean elevation during the shift


@dataclass
class TempRhythm:
    shifts: list = field(default_factory=list)
    current_state: str = "baseline"  # "baseline" | "elevated"
    summary: str = ""


def detect_shifts(series: list[dict]) -> TempRhythm:
    """`series` is the client's skin_temp_series output, oldest first."""
    points = [
        (d["date"], d["nightly_relative"])
        for d in series
        if d.get("nightly_relative") is not None
    ]
    if len(points) < BASELINE_WINDOW + MIN_SHIFT_DAYS:
        return TempRhythm(summary="Not enough temperature data for shift detection.")

    # Baseline = trailing median of recent NON-elevated nights, so a sustained
    # shift (e.g. a ~12-night luteal elevation) stays flagged for its whole
    # duration instead of being absorbed into the baseline after a few days.
    baseline_pool: list[float] = []
    elevated_flags: list[bool] = []
    elevations: list[float] = []
    for _date, value in points:
        if len(baseline_pool) < BASELINE_WINDOW:
            baseline_pool.append(value)
            elevated_flags.append(False)
            elevations.append(0.0)
            continue
        baseline = statistics.median(baseline_pool[-BASELINE_WINDOW:])
        elevation = value - baseline
        is_elevated = elevation >= SHIFT_THRESHOLD
        elevated_flags.append(is_elevated)
        elevations.append(elevation)
        if not is_elevated:
            baseline_pool.append(value)

    shifts: list[TempShift] = []
    run: list[int] = []
    for i, flag in enumerate(elevated_flags):
        if flag:
            run.append(i)
        else:
            if len(run) >= MIN_SHIFT_DAYS:
                shifts.append(_make_shift(points, elevations, run))
            run = []
    if len(run) >= MIN_SHIFT_DAYS:
        shifts.append(_make_shift(points, elevations, run))

    # currently elevated if the last 2+ nights are flagged (shift may still be forming)
    tail = 0
    for flag in reversed(elevated_flags):
        if not flag:
            break
        tail += 1
    state = "elevated" if tail >= 2 else "baseline"

    if shifts:
        last = shifts[-1]
        summary = (
            f"{len(shifts)} sustained temperature shift(s) in this window; latest "
            f"{last.start} → {last.end} (+{last.magnitude}°C over {last.days} nights). "
            "Sustained shifts can reflect cycle phase, illness onset, or environment."
        )
    else:
        summary = "No sustained temperature shifts detected in this window."
    if state == "elevated":
        summary += " Temperature is currently elevated vs your trailing baseline."
    return TempRhythm(shifts=shifts, current_state=state, summary=summary)


def _make_shift(points: list, elevations: list[float], run: list[int]) -> TempShift:
    return TempShift(
        start=points[run[0]][0],
        end=points[run[-1]][0],
        days=len(run),
        magnitude=round(statistics.fmean(elevations[i] for i in run), 2),
    )
