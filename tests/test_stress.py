import datetime as dt

from sense2.demo_data import DemoClient
from sense2.stress import compute_stress, stress_for_date


def _flat_day(resting=60, bpm=62):
    samples = [(f"{m // 60:02d}:{m % 60:02d}:00", bpm) for m in range(1440)]
    return {"date": "2026-06-01", "resting_hr": resting, "samples": samples}


def _no_steps():
    return {"date": "2026-06-01", "samples": [(f"{m // 60:02d}:{m % 60:02d}:00", 0) for m in range(1440)]}


def test_calm_day_scores_low():
    result = compute_stress(_flat_day(), _no_steps())
    assert result.daily_avg < 10
    assert result.peak < 25
    assert result.episodes == []


def test_sustained_hr_spike_without_movement_scores_high():
    heart = _flat_day()
    heart["samples"] = [
        (t, 100 if 600 <= i < 700 else bpm) for i, (t, bpm) in enumerate(heart["samples"])
    ]
    result = compute_stress(heart, _no_steps())
    spike_scores = [s for t, s, a in result.samples[640:700]]
    assert max(spike_scores) > 60
    assert result.episodes, "a sustained spike should register as an episode"


def test_activity_masks_stress():
    heart = _flat_day()
    heart["samples"] = [
        (t, 140 if 600 <= i < 700 else bpm) for i, (t, bpm) in enumerate(heart["samples"])
    ]
    steps = _no_steps()
    steps["samples"] = [
        (t, 100 if 595 <= i < 705 else 0) for i, (t, v) in enumerate(steps["samples"])
    ]
    result = compute_stress(heart, steps)
    active_flags = [a for t, s, a in result.samples[620:700]]
    assert all(active_flags), "high-step periods must be flagged active"
    assert result.peak < 30, "exercise HR must not count as stress"


def test_low_hrv_amplifies_score():
    heart = _flat_day(bpm=75)
    base = compute_stress(heart, _no_steps())
    stressed = compute_stress(heart, _no_steps(), hrv_today=25, hrv_baseline=45)
    assert stressed.hrv_modifier > 1.0
    assert stressed.daily_avg > base.daily_avg


def test_stress_for_date_with_demo_client():
    today = dt.date(2026, 6, 10)
    result = stress_for_date(DemoClient(today=today), today)
    assert 0 <= result.daily_avg <= 100
    assert len(result.samples) == 1440
    # the demo day includes an 11:00 meeting spike with no movement
    assert any(e.start >= "10:5" and e.start <= "12:0" for e in result.episodes)
