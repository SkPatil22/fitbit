import datetime as dt

from sense2.demo_data import DemoClient
from sense2.training import compute_status, day_trimp, training_for_range


def _day(bpm_blocks, resting=60, date="2026-06-01"):
    """bpm_blocks: list of (minutes, bpm) tuples summing to <= 1440."""
    samples, minute = [], 0
    for count, bpm in bpm_blocks:
        for _ in range(count):
            samples.append((f"{minute // 60:02d}:{minute % 60:02d}:00", bpm))
            minute += 1
    return {"date": date, "resting_hr": resting, "samples": samples}


def test_rest_day_scores_near_zero():
    load = day_trimp(_day([(1440, 62)]))
    assert load.trimp < 5
    assert all(v == 0 for v in load.zone_minutes.values())


def test_workout_scores_and_lands_in_zone():
    # 45 min at ~79% HRR (60 + 0.79*127 ≈ 160 bpm), rest of day quiet
    load = day_trimp(_day([(600, 62), (45, 160), (795, 62)], resting=60))
    assert load.trimp > 50
    assert load.zone_minutes["hard"] >= 40


def test_harder_effort_scores_disproportionately_more():
    easy = day_trimp(_day([(60, 100), (1380, 62)]))
    hard = day_trimp(_day([(60, 160), (1380, 62)]))
    # Banister weighting: same duration, much more than linear difference
    assert hard.trimp > easy.trimp * 2.5


def test_steady_routine_is_neutral():
    loads = [day_trimp(_day([(60, 150), (1380, 62)], date=f"2026-05-{i:02d}")) for i in range(1, 29)]
    status = compute_status(loads)
    # constant load: fitness == fatigue == steady state -> form ~ 0
    assert abs(status.form) < 5
    assert status.label == "Neutral"
    assert len(status.fitness_series) == 28


def test_sudden_ramp_drives_form_negative():
    quiet = [day_trimp(_day([(1440, 62)], date=f"2026-05-{i:02d}")) for i in range(1, 22)]
    heavy = [day_trimp(_day([(90, 160), (1350, 62)], date=f"2026-05-{21 + i:02d}")) for i in range(1, 8)]
    status = compute_status(quiet + heavy)
    assert status.fatigue > status.fitness
    assert status.form < -10


def test_taper_drives_form_positive():
    heavy = [day_trimp(_day([(90, 160), (1350, 62)], date=f"2026-05-{i:02d}")) for i in range(1, 22)]
    quiet = [day_trimp(_day([(1440, 62)], date=f"2026-05-{21 + i:02d}")) for i in range(1, 8)]
    status = compute_status(heavy + quiet)
    assert status.form > 5
    assert status.label == "Fresh"


def test_training_for_range_demo():
    status = training_for_range(DemoClient(today=dt.date(2026, 6, 10)), dt.date(2026, 6, 10), days=10)
    assert len(status.days) == 10
    assert status.weekly_trimp > 0  # demo includes a daily workout
