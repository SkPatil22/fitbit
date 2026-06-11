"""n=1 experiment journal: tag days, then measure what the tag does to you.

The r/QuantifiedSelf classic — log "alcohol", "caffeine-pm", "late-workout",
"melatonin" against calendar days, then compare nightly biometrics on tagged
vs untagged days. A tag on day D is scored against the night D -> D+1, which
is how Fitbit dates its nightly metrics (HRV/RHR/sleep recorded for the
morning of D+1). Reference point: WHOOP's published population effect of one
drink is roughly HRV -7 ms and resting HR +3 bpm.

Effects report the mean difference, Cohen's d and a Welch t-statistic; |t|>2
with n>=5 per group is flagged "likely real".
"""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_JOURNAL_PATH = Path.home() / ".sense2" / "journal.json"

METRICS = ("hrv_rmssd", "resting_hr", "minutes_asleep", "efficiency")


class Journal:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or DEFAULT_JOURNAL_PATH)
        self._days: dict[str, list[str]] = {}
        if self.path.exists():
            self._days = json.loads(self.path.read_text())

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._days, indent=2, sort_keys=True))

    def add(self, date: dt.date, tag: str) -> None:
        tags = self._days.setdefault(str(date), [])
        if tag not in tags:
            tags.append(tag)
        self._save()

    def remove(self, date: dt.date, tag: str) -> None:
        tags = self._days.get(str(date), [])
        if tag in tags:
            tags.remove(tag)
            if not tags:
                del self._days[str(date)]
            self._save()

    def tags_on(self, date: dt.date) -> list[str]:
        return self._days.get(str(date), [])

    def all_tags(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for tags in self._days.values():
            for t in tags:
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def tagged_dates(self, tag: str) -> set[str]:
        return {d for d, tags in self._days.items() if tag in tags}


@dataclass
class Effect:
    metric: str
    tagged_mean: float
    untagged_mean: float
    delta: float
    pct: float
    n_tagged: int
    n_untagged: int
    cohens_d: float
    t_stat: float
    verdict: str  # "likely real" | "weak signal" | "no clear effect"


@dataclass
class TagReport:
    tag: str
    effects: list = field(default_factory=list)


def _welch_t(a: list[float], b: list[float]) -> float:
    va, vb = statistics.variance(a), statistics.variance(b)
    se = math.sqrt(va / len(a) + vb / len(b))
    return (statistics.fmean(a) - statistics.fmean(b)) / se if se else 0.0


def compare_groups(metric: str, tagged: list[float], untagged: list[float]) -> Effect | None:
    if len(tagged) < 2 or len(untagged) < 2:
        return None
    mean_t, mean_u = statistics.fmean(tagged), statistics.fmean(untagged)
    pooled = statistics.pstdev(tagged + untagged) or 1e-9
    d = (mean_t - mean_u) / pooled
    t = _welch_t(tagged, untagged)
    if abs(t) >= 2 and min(len(tagged), len(untagged)) >= 5:
        verdict = "likely real"
    elif abs(t) >= 1.3:
        verdict = "weak signal"
    else:
        verdict = "no clear effect"
    return Effect(
        metric=metric,
        tagged_mean=round(mean_t, 1),
        untagged_mean=round(mean_u, 1),
        delta=round(mean_t - mean_u, 1),
        pct=round(100 * (mean_t - mean_u) / mean_u, 1) if mean_u else 0.0,
        n_tagged=len(tagged),
        n_untagged=len(untagged),
        cohens_d=round(d, 2),
        t_stat=round(t, 2),
        verdict=verdict,
    )


def analyze_tag(client, journal: Journal, tag: str, end: dt.date, days: int = 90) -> TagReport:
    """Compare nightly metrics on nights following tagged vs untagged days."""
    start = end - dt.timedelta(days=days)
    hrv = {d["date"]: d["rmssd"] for d in client.hrv_series(start, end)}
    rhr = {d["date"]: d["resting_hr"] for d in client.resting_hr_series(start, end)}
    sleep = {d["date"]: d for d in client.sleep_series(start, end)}

    per_night = {}
    for key in set(hrv) | set(rhr) | set(sleep):
        s = sleep.get(key, {})
        per_night[key] = {
            "hrv_rmssd": hrv.get(key),
            "resting_hr": rhr.get(key),
            "minutes_asleep": s.get("minutes_asleep"),
            "efficiency": s.get("efficiency"),
        }

    tagged_dates = journal.tagged_dates(tag)
    report = TagReport(tag=tag)
    for metric in METRICS:
        tagged_vals, untagged_vals = [], []
        for night_key, values in per_night.items():
            v = values[metric]
            if v is None:
                continue
            # the night dated D reflects the previous calendar day D-1
            previous_day = str(dt.date.fromisoformat(night_key) - dt.timedelta(days=1))
            (tagged_vals if previous_day in tagged_dates else untagged_vals).append(v)
        effect = compare_groups(metric, tagged_vals, untagged_vals)
        if effect:
            report.effects.append(effect)
    return report


def render_report(report: TagReport) -> str:
    if not report.effects:
        return f'No analyzable data for tag "{report.tag}" (need ≥2 tagged days with metrics).'
    pretty = {
        "hrv_rmssd": ("HRV (RMSSD)", "ms"),
        "resting_hr": ("Resting HR", "bpm"),
        "minutes_asleep": ("Sleep duration", "min"),
        "efficiency": ("Sleep efficiency", "%"),
    }
    lines = [f'Effect of "{report.tag}" on the following night '
             f"({report.effects[0].n_tagged} tagged vs {report.effects[0].n_untagged} normal days):"]
    for e in report.effects:
        name, unit = pretty[e.metric]
        sign = "+" if e.delta >= 0 else ""
        lines.append(
            f"  {name:<17} {sign}{e.delta} {unit} ({sign}{e.pct}%)  "
            f"[d={e.cohens_d}, t={e.t_stat}] — {e.verdict}"
        )
    return "\n".join(lines)
