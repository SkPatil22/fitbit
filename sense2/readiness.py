"""Daily readiness / recovery score (Whoop- and Oura-style) from Sense 2 data.

Combines three signals against personal baselines:
  * HRV (daily RMSSD) vs 30-day baseline — 40%
  * resting heart rate vs 30-day baseline (lower is better) — 30%
  * last night's sleep (duration vs 8h need + efficiency) — 30%
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

SLEEP_NEED_MINUTES = 480


@dataclass
class ReadinessResult:
    date: str
    score: int
    hrv_score: int
    rhr_score: int
    sleep_score: int
    label: str
    recommendation: str


def _interp(x: float, points: list[tuple[float, float]]) -> float:
    """Piecewise-linear interpolation over sorted (x, y) control points."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _label(score: int) -> tuple[str, str]:
    if score >= 80:
        return "Primed", "Green light — a hard workout or big day will land well."
    if score >= 60:
        return "Good", "Solid recovery. Normal training and workload are fine."
    if score >= 40:
        return "Fair", "Partially recovered — keep intensity moderate today."
    return "Run down", "Recovery is poor. Prioritize rest, hydration and an early night."


def compute_readiness(
    date: dt.date,
    hrv_today: float | None,
    hrv_baseline: float | None,
    rhr_today: float | None,
    rhr_baseline: float | None,
    minutes_asleep: float | None,
    sleep_efficiency: float | None,
) -> ReadinessResult:
    if hrv_today and hrv_baseline:
        ratio = hrv_today / hrv_baseline
        hrv_score = _interp(ratio, [(0.6, 0), (0.7, 25), (0.85, 55), (1.0, 85), (1.1, 100)])
    else:
        hrv_score = 60  # neutral when no data

    if rhr_today and rhr_baseline:
        delta = rhr_baseline - rhr_today  # positive = lower than usual = good
        rhr_score = _interp(delta, [(-8, 0), (-6, 20), (-3, 50), (0, 80), (2, 100)])
    else:
        rhr_score = 60

    if minutes_asleep:
        duration = min(minutes_asleep / SLEEP_NEED_MINUTES, 1.0) * 100
        efficiency = _interp(sleep_efficiency or 85, [(70, 40), (85, 75), (90, 90), (95, 100)])
        sleep_score = 0.7 * duration + 0.3 * efficiency
    else:
        sleep_score = 60

    score = round(0.4 * hrv_score + 0.3 * rhr_score + 0.3 * sleep_score)
    label, recommendation = _label(score)
    return ReadinessResult(
        date=str(date),
        score=score,
        hrv_score=round(hrv_score),
        rhr_score=round(rhr_score),
        sleep_score=round(sleep_score),
        label=label,
        recommendation=recommendation,
    )


def readiness_for_date(client, date: dt.date, baseline_days: int = 30) -> ReadinessResult:
    start = date - dt.timedelta(days=baseline_days)
    end = date - dt.timedelta(days=1)

    hrv = client.hrv_daily(date)
    hrv_baseline = client.hrv_series(start, end)
    rhr_baseline = client.resting_hr_series(start, end)
    sleep = client.sleep_summary(date)
    rhr_today = client.heart_intraday(date)["resting_hr"]

    return compute_readiness(
        date,
        hrv_today=hrv["rmssd"] if hrv else None,
        hrv_baseline=(
            sum(d["rmssd"] for d in hrv_baseline) / len(hrv_baseline) if hrv_baseline else None
        ),
        rhr_today=rhr_today,
        rhr_baseline=(
            sum(d["resting_hr"] for d in rhr_baseline) / len(rhr_baseline)
            if rhr_baseline
            else None
        ),
        minutes_asleep=sleep["minutes_asleep"] if sleep else None,
        sleep_efficiency=sleep["efficiency"] if sleep else None,
    )
