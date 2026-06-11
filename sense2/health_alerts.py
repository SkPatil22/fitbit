"""Illness early-warning from nightly biometrics, in the spirit of the
Stanford wearables studies: pre-symptomatic infection shows up as elevated
resting heart rate, breathing rate and skin temperature plus suppressed HRV,
often days before symptoms.

Each metric is compared to a trailing personal baseline (mean/std over up to
30 prior days). A metric "fires" when today's value is both statistically
unusual (|z| >= 2) and physiologically meaningful (absolute floor). One firing
metric -> WATCH, two or more -> ALERT.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, field

MIN_BASELINE_DAYS = 7


@dataclass
class Signal:
    metric: str
    today: float
    baseline: float
    z: float
    message: str


@dataclass
class HealthStatus:
    date: str
    level: str  # "ok" | "watch" | "alert"
    signals: list = field(default_factory=list)
    summary: str = ""


def _check(
    name: str,
    today: float | None,
    history: list[float],
    direction: int,  # +1 = elevated is bad, -1 = suppressed is bad
    abs_floor: float,
    std_floor: float,
    unit: str,
) -> Signal | None:
    if today is None or len(history) < MIN_BASELINE_DAYS:
        return None
    mean = statistics.fmean(history)
    std = max(statistics.stdev(history), std_floor)
    z = (today - mean) / std
    deviation = (today - mean) * direction
    if z * direction >= 2.0 and deviation >= abs_floor:
        word = "elevated" if direction > 0 else "suppressed"
        return Signal(
            metric=name,
            today=round(today, 2),
            baseline=round(mean, 2),
            z=round(z, 2),
            message=(
                f"{name} {word}: {today:.1f}{unit} vs baseline "
                f"{mean:.1f}{unit} (z={z:+.1f})"
            ),
        )
    return None


def evaluate_day(
    date: dt.date,
    rhr_today: float | None,
    rhr_history: list[float],
    br_today: float | None,
    br_history: list[float],
    temp_today: float | None,
    temp_history: list[float],
    hrv_today: float | None,
    hrv_history: list[float],
) -> HealthStatus:
    signals = [
        s
        for s in (
            _check("Resting heart rate", rhr_today, rhr_history, +1, 3.0, 1.0, " bpm"),
            _check("Breathing rate", br_today, br_history, +1, 1.5, 0.4, " br/min"),
            _check("Skin temperature", temp_today, temp_history, +1, 0.5, 0.15, "°C"),
            _check("HRV (RMSSD)", hrv_today, hrv_history, -1, 8.0, 2.5, " ms"),
        )
        if s
    ]
    if len(signals) >= 2:
        level, summary = "alert", (
            f"{len(signals)} biometrics deviate from your baseline — a pattern "
            "consistent with early illness or heavy strain. Consider taking it "
            "easy and monitoring symptoms. (Not a medical diagnosis.)"
        )
    elif len(signals) == 1:
        level, summary = "watch", (
            f"{signals[0].metric} is off baseline today. One signal alone is "
            "often noise (alcohol, late workout, hot room) — worth watching."
        )
    else:
        level, summary = "ok", "All nightly biometrics are within your normal range."
    return HealthStatus(date=str(date), level=level, signals=signals, summary=summary)


def health_check(client, date: dt.date, baseline_days: int = 30) -> HealthStatus:
    """Fetch trailing series from a client and evaluate `date`."""
    start = date - dt.timedelta(days=baseline_days)
    end = date - dt.timedelta(days=1)

    rhr = {d["date"]: d["resting_hr"] for d in client.resting_hr_series(start, date)}
    br = {d["date"]: d["rate"] for d in client.breathing_rate_series(start, date)}
    temp = {
        d["date"]: d["nightly_relative"] for d in client.skin_temp_series(start, date)
    }
    hrv = {d["date"]: d["rmssd"] for d in client.hrv_series(start, date)}

    key = str(date)
    history = lambda series: [v for k, v in series.items() if k != key and v is not None]  # noqa: E731
    return evaluate_day(
        date,
        rhr.get(key), history(rhr),
        br.get(key), history(br),
        temp.get(key), history(temp),
        hrv.get(key), history(hrv),
    )
