"""Session analyzer: the "my heart rate during the horror movie" feature.

People love posting annotated heart-rate graphs of movies, interviews, dates,
penalty shootouts. Given a date, a time window and a label, this slices the
intraday data and produces the stats plus a shareable text card:

    python -m sense2 session --demo --date 2026-06-10 \
        --from 21:00 --to 23:15 --label "Hereditary"
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .stress import compute_stress


@dataclass
class Peak:
    time: str
    bpm: int


@dataclass
class SessionResult:
    label: str
    date: str
    start: str
    end: str
    avg_hr: int
    max_hr: int
    min_hr: int
    resting_hr: int
    minutes: int
    elevated_minutes: int  # minutes >= 20% above resting
    active_minutes: int  # movement (not autonomic arousal)
    avg_stress: int
    peaks: list = field(default_factory=list)  # top moments, Peak
    samples: list = field(default_factory=list)  # [(time, bpm)] within window


def _in_window(t: str, start: str, end: str) -> bool:
    return start <= t[:5] < end


def analyze_session(client, date: dt.date, start: str, end: str, label: str) -> SessionResult:
    heart = client.heart_intraday(date)
    steps = client.steps_intraday(date)
    stress = compute_stress(heart, steps)

    samples = [(t, bpm) for t, bpm in heart["samples"] if _in_window(t, start, end)]
    if not samples:
        raise ValueError(f"no heart rate samples between {start} and {end} on {date}")
    resting = heart.get("resting_hr") or 60
    bpms = [b for _, b in samples]

    stress_window = [(t, s, a) for t, s, a in stress.samples if _in_window(t, start, end)]
    inactive_scores = [s for _, s, a in stress_window if not a] or [0]

    return SessionResult(
        label=label,
        date=str(date),
        start=start,
        end=end,
        avg_hr=round(sum(bpms) / len(bpms)),
        max_hr=max(bpms),
        min_hr=min(bpms),
        resting_hr=resting,
        minutes=len(samples),
        elevated_minutes=sum(1 for b in bpms if b >= resting * 1.2),
        active_minutes=sum(1 for _, _, a in stress_window if a),
        avg_stress=round(sum(inactive_scores) / len(inactive_scores)),
        peaks=_top_peaks(samples),
        samples=samples,
    )


def _top_peaks(samples: list, count: int = 3, separation_min: int = 5) -> list[Peak]:
    """Highest HR moments, at least `separation_min` minutes apart."""
    ordered = sorted(samples, key=lambda s: s[1], reverse=True)
    peaks: list[Peak] = []
    for t, bpm in ordered:
        minute = int(t[:2]) * 60 + int(t[3:5])
        if all(abs(minute - (int(p.time[:2]) * 60 + int(p.time[3:5]))) >= separation_min for p in peaks):
            peaks.append(Peak(time=t[:5], bpm=bpm))
        if len(peaks) == count:
            break
    return sorted(peaks, key=lambda p: p.time)


def render_card(result: SessionResult, width: int = 48) -> str:
    """Plain-text shareable card with an inline sparkline."""
    blocks = " ▁▂▃▄▅▆▇█"
    bpms = [b for _, b in result.samples]
    step = max(len(bpms) // width, 1)
    sampled = [bpms[i] for i in range(0, len(bpms), step)]
    lo, hi = min(sampled), max(sampled)
    span = (hi - lo) or 1
    spark = "".join(blocks[1 + round((v - lo) / span * 7)] for v in sampled)

    lines = [
        f"❤️  {result.label} — {result.date} {result.start}–{result.end}",
        f"   {spark}",
        f"   avg {result.avg_hr} bpm · peak {result.max_hr} · low {result.min_hr} "
        f"(resting {result.resting_hr})",
        f"   {result.elevated_minutes}/{result.minutes} min elevated ≥20% over resting · "
        f"avg stress {result.avg_stress}/100",
    ]
    if result.peaks:
        moments = ", ".join(f"{p.time} ({p.bpm} bpm)" for p in result.peaks)
        lines.append(f"   spikes: {moments}")
    return "\n".join(lines)
