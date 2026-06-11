"""Intraday stress estimation from heart rate, activity and HRV.

The Sense 2's on-watch EDA/stress score is not exposed through the public Web
API, so — like the community projects this is modeled on — we estimate stress
from the signals that ARE available:

  * heart rate elevation above resting while the wearer is NOT moving
    (autonomic arousal rather than exercise), using step counts to mask
    physical activity, and
  * suppression of the day's HRV (RMSSD) relative to a personal baseline,
    which amplifies or dampens the heart-rate-derived score.

Scores are 0-100: <25 calm, 25-50 mild, 50-75 moderate, >=75 high.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

ZONES = (("calm", 0, 25), ("mild", 25, 50), ("moderate", 50, 75), ("high", 75, 101))

ACTIVE_STEPS_PER_10MIN = 350  # above this, HR elevation is treated as exercise
SMOOTH_MINUTES = 10


@dataclass
class StressEpisode:
    start: str
    end: str
    peak: int
    avg: int


@dataclass
class StressResult:
    date: str
    samples: list  # [(HH:MM:SS, score, active)]
    daily_avg: int
    peak: int
    zone_minutes: dict
    episodes: list = field(default_factory=list)
    hrv_modifier: float = 1.0


def compute_stress(
    heart: dict,
    steps: dict,
    hrv_today: float | None = None,
    hrv_baseline: float | None = None,
) -> StressResult:
    """Compute an intraday stress curve and daily summary.

    `heart`/`steps` are the normalized intraday dicts from the client layer.
    """
    resting = heart.get("resting_hr") or 60

    # Low HRV relative to baseline amplifies the score (sympathetic dominance);
    # ratio 1.0 -> x1.0, ratio 0.6 -> x1.4 (capped), ratio 1.3 -> x0.7 (floor).
    modifier = 1.0
    if hrv_today and hrv_baseline:
        modifier = min(1.4, max(0.7, 2.0 - hrv_today / hrv_baseline))

    step_by_min = {t[:5]: v for t, v in steps.get("samples", [])}

    raw: list[tuple[str, float, bool]] = []
    window: list[int] = []
    for t, bpm in heart.get("samples", []):
        window.append(step_by_min.get(t[:5], 0))
        if len(window) > 10:
            window.pop(0)
        active = sum(window) > ACTIVE_STEPS_PER_10MIN

        # HR elevation of 8%..60% above resting maps onto 0..100.
        pct = (bpm - resting) / resting
        score = max(0.0, min(100.0, (pct - 0.08) / 0.52 * 100)) * modifier
        if active:
            score = 0.0  # exertion, not stress
        raw.append((t, score, active))

    # Exponential smoothing so brief HR blips don't register as stress.
    alpha = 2 / (SMOOTH_MINUTES + 1)
    smoothed: list[tuple[str, int, bool]] = []
    ema = 0.0
    for t, score, active in raw:
        ema = alpha * score + (1 - alpha) * ema
        smoothed.append((t, round(min(100, ema)), active))

    inactive = [(t, s) for t, s, a in smoothed if not a]
    scores = [s for _, s in inactive] or [0]
    zone_minutes = {
        name: sum(1 for s in scores if lo <= s < hi) for name, lo, hi in ZONES
    }

    return StressResult(
        date=heart.get("date", ""),
        samples=smoothed,
        daily_avg=round(sum(scores) / len(scores)),
        peak=max(scores),
        zone_minutes=zone_minutes,
        episodes=_find_episodes(smoothed),
        hrv_modifier=round(modifier, 2),
    )


def _find_episodes(samples, threshold: int = 50, min_minutes: int = 10) -> list[StressEpisode]:
    """Contiguous runs of moderate-or-higher stress lasting >= min_minutes."""
    episodes = []
    run: list[tuple[str, int]] = []
    for t, score, active in samples:
        if score >= threshold and not active:
            run.append((t, score))
        else:
            if len(run) >= min_minutes:
                vals = [s for _, s in run]
                episodes.append(
                    StressEpisode(
                        start=run[0][0][:5],
                        end=run[-1][0][:5],
                        peak=max(vals),
                        avg=round(sum(vals) / len(vals)),
                    )
                )
            run = []
    if len(run) >= min_minutes:
        vals = [s for _, s in run]
        episodes.append(
            StressEpisode(run[0][0][:5], run[-1][0][:5], max(vals), round(sum(vals) / len(vals)))
        )
    return episodes


def stress_for_date(client, date: dt.date, baseline_days: int = 30) -> StressResult:
    """Convenience wrapper: fetch inputs from a client and score the day."""
    heart = client.heart_intraday(date)
    steps = client.steps_intraday(date)
    hrv = client.hrv_daily(date)
    baseline = client.hrv_series(date - dt.timedelta(days=baseline_days), date - dt.timedelta(days=1))
    baseline_rmssd = (
        sum(d["rmssd"] for d in baseline) / len(baseline) if baseline else None
    )
    return compute_stress(
        heart,
        steps,
        hrv_today=hrv["rmssd"] if hrv else None,
        hrv_baseline=baseline_rmssd,
    )
