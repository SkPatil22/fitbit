"""Monthly Sleep Profile — recreation of Fitbit Premium's "sleep animal".

Premium analyzes a month of sleep and assigns one of six animals (bear,
dolphin, giraffe, hedgehog, parrot, tortoise). This rebuilds the idea from
the same signals the Web API exposes: duration, schedule consistency
(std-dev of the sleep midpoint), deep/REM share and efficiency. The animal
heuristics follow Fitbit's published archetype descriptions; like the
original, it's a fun lens on a month of data, not a diagnosis.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass

MIN_NIGHTS = 10

ANIMALS = {
    "bear": ("🐻", "Long, sound, consistent sleep on a steady schedule — the "
             "archetype everyone else is jealous of."),
    "dolphin": ("🐬", "A light sleeper: shorter, more fragmented nights on a "
                "variable schedule. Dolphins sleep with one eye open."),
    "giraffe": ("🦒", "Short total sleep — you function on less than most, "
                "by choice or by calendar."),
    "hedgehog": ("🦔", "A night owl: later bedtimes and shorter, lighter "
                 "sleep than the early-to-bed crowd."),
    "parrot": ("🦜", "Consistent schedule and solid efficiency with average "
               "duration — dependable, social-hours sleep."),
    "tortoise": ("🐢", "Plenty of time in bed but lighter, more interrupted "
                 "sleep — slow and steady, with room to consolidate."),
}


@dataclass
class SleepProfile:
    animal: str
    emoji: str
    description: str
    nights: int
    avg_duration_min: int
    midpoint_std_min: int  # schedule consistency: lower = steadier
    avg_midpoint: str
    deep_pct: float
    rem_pct: float
    avg_efficiency: float


def _midpoint_minutes_after_noon(start: dt.datetime, end: dt.datetime) -> float:
    mid = start + (end - start) / 2
    return ((mid.hour - 12) % 24) * 60 + mid.minute


def compute_profile(sleep_series: list[dict]) -> SleepProfile | None:
    nights = [
        s for s in sleep_series
        if s.get("start") and s.get("minutes_asleep") and s.get("stages")
    ]
    if len(nights) < MIN_NIGHTS:
        return None

    durations, midpoints, deep_shares, rem_shares, efficiencies = [], [], [], [], []
    for s in nights:
        start = dt.datetime.fromisoformat(s["start"].split(".")[0])
        end = dt.datetime.fromisoformat(s["end"].split(".")[0])
        asleep = s["minutes_asleep"]
        durations.append(asleep)
        midpoints.append(_midpoint_minutes_after_noon(start, end))
        deep_shares.append(s["stages"].get("deep", 0) / asleep)
        rem_shares.append(s["stages"].get("rem", 0) / asleep)
        efficiencies.append(s.get("efficiency") or 85)

    avg_dur = statistics.fmean(durations)
    mid_std = statistics.stdev(midpoints)
    avg_mid = statistics.fmean(midpoints)
    deep_pct = 100 * statistics.fmean(deep_shares)
    rem_pct = 100 * statistics.fmean(rem_shares)
    efficiency = statistics.fmean(efficiencies)

    # Archetype rules, checked in priority order (Fitbit-style descriptions).
    late_midpoint = avg_mid > 16 * 60  # midpoint after 4 AM
    if avg_dur < 390:
        animal = "hedgehog" if late_midpoint else "giraffe"
    elif mid_std > 75 or (efficiency < 88 and mid_std > 50):
        animal = "dolphin"
    elif avg_dur >= 450 and mid_std <= 45 and deep_pct >= 17:
        animal = "bear"
    elif efficiency >= 91 and mid_std <= 60:
        animal = "parrot"
    else:
        animal = "tortoise"

    emoji, description = ANIMALS[animal]
    mid_clock = (12 * 60 + round(avg_mid)) % (24 * 60)
    return SleepProfile(
        animal=animal,
        emoji=emoji,
        description=description,
        nights=len(nights),
        avg_duration_min=round(avg_dur),
        midpoint_std_min=round(mid_std),
        avg_midpoint=f"{mid_clock // 60:02d}:{mid_clock % 60:02d}",
        deep_pct=round(deep_pct, 1),
        rem_pct=round(rem_pct, 1),
        avg_efficiency=round(efficiency, 1),
    )


def profile_for_range(client, end: dt.date, days: int = 28) -> SleepProfile | None:
    return compute_profile(client.sleep_series(end - dt.timedelta(days=days - 1), end))
