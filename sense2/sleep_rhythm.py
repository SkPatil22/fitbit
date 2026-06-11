"""Sleep rhythm analytics: regularity, social jetlag and sleep debt.

Three community-favorite metrics the Fitbit app doesn't surface:

* Sleep Regularity Index (SRI) — probability of being in the same state
  (asleep/awake) at the same clock minute on consecutive days, rescaled to
  0..100 (Phillips et al.); computed here from main-sleep intervals.
* Social jetlag — difference between the median sleep midpoint on free nights
  (Fri/Sat nights) and work nights (Roenneberg); >1h is the classic threshold
  associated with worse health outcomes.
* Sleep debt — rolling shortfall vs an 8h/night need over the last 14 days.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass

SLEEP_NEED_MINUTES = 480
DEBT_WINDOW_DAYS = 14
MINUTES_PER_DAY = 24 * 60


@dataclass
class SleepRhythm:
    sri: float | None  # 0..100
    social_jetlag_minutes: int | None
    avg_midpoint: str  # "03:24"
    debt_minutes: int
    nights: int
    summary: str


def _parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.split(".")[0])


def _asleep_vector(start: dt.datetime, end: dt.datetime, anchor: dt.date) -> list[bool]:
    """Minute-resolution asleep/awake vector for the 24h starting at noon on
    `anchor - 1 day` — anchoring at noon keeps a whole night in one vector."""
    vec = [False] * MINUTES_PER_DAY
    window_start = dt.datetime.combine(anchor - dt.timedelta(days=1), dt.time(12, 0))
    i = max(0, int((start - window_start).total_seconds() // 60))
    j = min(MINUTES_PER_DAY, int((end - window_start).total_seconds() // 60))
    for m in range(i, j):
        vec[m] = True
    return vec


def _midpoint_minutes(start: dt.datetime, end: dt.datetime) -> float:
    """Sleep midpoint expressed as minutes after noon (so 3:00 AM = 900)."""
    mid = start + (end - start) / 2
    return ((mid.hour - 12) % 24) * 60 + mid.minute


def compute_rhythm(sleep_series: list[dict]) -> SleepRhythm:
    nights = [
        (dt.date.fromisoformat(s["date"]), _parse(s["start"]), _parse(s["end"]), s["minutes_asleep"])
        for s in sleep_series
        if s.get("start") and s.get("end") and s.get("minutes_asleep")
    ]
    if len(nights) < 5:
        return SleepRhythm(None, None, "--:--", 0, len(nights),
                           "Not enough nights with sleep data (need 5+).")

    # SRI over consecutive-night pairs
    vectors = {date: _asleep_vector(start, end, date) for date, start, end, _ in nights}
    agreements = []
    for date in vectors:
        nxt = date + dt.timedelta(days=1)
        if nxt in vectors:
            same = sum(a == b for a, b in zip(vectors[date], vectors[nxt]))
            agreements.append(same / MINUTES_PER_DAY)
    # Phillips et al. scale (-100..100); clamp at 0 for display sanity
    sri = round(max(0.0, -100 + 200 * statistics.fmean(agreements)), 1) if agreements else None

    # social jetlag: free nights = those starting Friday or Saturday evening
    free, work = [], []
    for date, start, end, _ in nights:
        midpoint = _midpoint_minutes(start, end)
        (free if start.weekday() in (4, 5) else work).append(midpoint)
    jetlag = (
        round(abs(statistics.median(free) - statistics.median(work)))
        if len(free) >= 2 and len(work) >= 2
        else None
    )

    all_midpoints = statistics.fmean(
        _midpoint_minutes(start, end) for _, start, end, _ in nights
    )
    mid_clock = (12 * 60 + round(all_midpoints)) % MINUTES_PER_DAY
    avg_midpoint = f"{mid_clock // 60:02d}:{mid_clock % 60:02d}"

    recent = [m for _, _, _, m in nights[-DEBT_WINDOW_DAYS:]]
    debt = sum(max(0, SLEEP_NEED_MINUTES - m) for m in recent)

    parts = []
    if sri is not None:
        parts.append(
            f"Sleep regularity {sri}/100 ("
            + ("very consistent" if sri >= 80 else "fairly consistent" if sri >= 60 else "irregular")
            + ")"
        )
    if jetlag is not None:
        parts.append(
            f"social jetlag {jetlag} min"
            + (" — over the 1h threshold linked to worse health" if jetlag > 60 else "")
        )
    parts.append(f"sleep debt {debt // 60}h{debt % 60:02d} over {len(recent)} nights")
    return SleepRhythm(
        sri=sri,
        social_jetlag_minutes=jetlag,
        avg_midpoint=avg_midpoint,
        debt_minutes=debt,
        nights=len(nights),
        summary="; ".join(parts) + ".",
    )


def rhythm_for_range(client, end: dt.date, days: int = 28) -> SleepRhythm:
    return compute_rhythm(client.sleep_series(end - dt.timedelta(days=days - 1), end))
