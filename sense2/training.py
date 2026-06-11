"""Training load from intraday heart rate: Banister TRIMP + fitness/fatigue/form.

Fitbit's Premium-only "Cardio Load" metric is a modified Banister TRIMP over
heart-rate reserve; this module rebuilds the same idea for free from the
intraday HR the Web API already provides, plus the classic impulse-response
("fitness/fatigue/form") model used by TrainingPeaks/choochoo:

  TRIMP/min = HRr * w1 * e^(w2 * HRr)        (Banister 1991; men 0.64/1.92,
                                              women 0.86/1.67)
  fitness (CTL) = 42-day EWMA of daily TRIMP
  fatigue (ATL) =  7-day EWMA of daily TRIMP
  form    (TSB) = fitness - fatigue

Minutes below 15% of heart-rate reserve are treated as rest and excluded so a
sedentary day scores ~0. Each day needs one intraday request, so a 42-day
window fits comfortably inside the 150 req/hour API budget.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

REST_HRR_THRESHOLD = 0.15
CTL_DAYS = 42
ATL_DAYS = 7

# %HRR zone boundaries (Karvonen-style)
ZONES = (
    ("light", 0.15, 0.40),
    ("moderate", 0.40, 0.60),  # the "zone 2" everyone chases
    ("cardio", 0.60, 0.75),
    ("hard", 0.75, 0.90),
    ("max", 0.90, 1.01),
)


@dataclass
class DayLoad:
    date: str
    trimp: float
    zone_minutes: dict


@dataclass
class TrainingStatus:
    days: list  # [DayLoad]
    fitness: float  # CTL
    fatigue: float  # ATL
    form: float  # TSB
    label: str
    advice: str
    weekly_trimp: float = 0.0
    fitness_series: list = field(default_factory=list)  # [(date, ctl, atl, tsb)]


def _max_hr(age: int) -> float:
    return 208 - 0.7 * age  # Tanaka et al.


def day_trimp(heart: dict, age: int = 30, sex: str = "male") -> DayLoad:
    """Banister TRIMP and %HRR zone minutes for one day of intraday HR."""
    resting = heart.get("resting_hr") or 60
    reserve = max(_max_hr(age) - resting, 30)
    w1, w2 = (0.86, 1.67) if sex == "female" else (0.64, 1.92)

    trimp = 0.0
    zone_minutes = {name: 0 for name, *_ in ZONES}
    for _t, bpm in heart.get("samples", []):
        hrr = max(0.0, min(1.0, (bpm - resting) / reserve))
        if hrr < REST_HRR_THRESHOLD:
            continue
        trimp += hrr * w1 * math.exp(w2 * hrr)
        for name, lo, hi in ZONES:
            if lo <= hrr < hi:
                zone_minutes[name] += 1
                break
    return DayLoad(date=heart.get("date", ""), trimp=round(trimp, 1), zone_minutes=zone_minutes)


def _form_label(tsb: float, ctl: float) -> tuple[str, str]:
    if tsb > 5:
        return "Fresh", "You're recovered relative to your fitness — a good day to push."
    if tsb > -10:
        return "Neutral", "Load and recovery are balanced. Train as planned."
    if tsb > -30:
        return "Productive overload", "You're building fitness, but watch for accumulating fatigue."
    return "Overreaching", "Fatigue is far ahead of fitness — back off before it bites."


def compute_status(days: list[DayLoad]) -> TrainingStatus:
    """Run the impulse-response model over a chronological list of DayLoads.

    CTL/ATL are seeded with the first week's mean load — cold-starting at zero
    would mislabel any steady routine as overreaching in short windows.
    """
    seed_days = days[: min(7, len(days))]
    ctl = atl = (
        sum(d.trimp for d in seed_days) / len(seed_days) if seed_days else 0.0
    )
    series = []
    for d in days:
        ctl += (d.trimp - ctl) / CTL_DAYS
        atl += (d.trimp - atl) / ATL_DAYS
        series.append((d.date, round(ctl, 1), round(atl, 1), round(ctl - atl, 1)))
    tsb = ctl - atl
    label, advice = _form_label(tsb, ctl)
    return TrainingStatus(
        days=days,
        fitness=round(ctl, 1),
        fatigue=round(atl, 1),
        form=round(tsb, 1),
        label=label,
        advice=advice,
        weekly_trimp=round(sum(d.trimp for d in days[-7:]), 1),
        fitness_series=series,
    )


def training_for_range(client, end: dt.date, days: int = CTL_DAYS) -> TrainingStatus:
    age = client.profile().get("age") or 30
    loads = []
    for offset in range(days - 1, -1, -1):
        date = end - dt.timedelta(days=offset)
        loads.append(day_trimp(client.heart_intraday(date), age=age))
    return compute_status(loads)
