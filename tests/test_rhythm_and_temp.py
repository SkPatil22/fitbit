import datetime as dt

from sense2.demo_data import DemoClient
from sense2.sleep_rhythm import compute_rhythm, rhythm_for_range
from sense2.temp_rhythm import detect_shifts

DATE = dt.date(2026, 6, 10)


def _night(date, bed_h, bed_m, asleep_min):
    prev = date - dt.timedelta(days=1)
    start = dt.datetime.combine(prev, dt.time(bed_h, bed_m))
    end = start + dt.timedelta(minutes=asleep_min + 30)
    return {
        "date": str(date),
        "start": start.isoformat() + ".000",
        "end": end.isoformat() + ".000",
        "minutes_asleep": asleep_min,
    }


def test_perfectly_regular_sleeper_has_high_sri_low_jetlag():
    series = [_night(DATE - dt.timedelta(days=i), 23, 0, 460) for i in range(27, -1, -1)]
    r = compute_rhythm(series)
    assert r.sri > 90
    assert r.social_jetlag_minutes is not None and r.social_jetlag_minutes < 15
    assert r.debt_minutes == 20 * 14  # 460 vs 480 need, 14-night window


def test_weekend_owl_has_social_jetlag():
    series = []
    for i in range(27, -1, -1):
        date = DATE - dt.timedelta(days=i)
        late = (date - dt.timedelta(days=1)).weekday() in (4, 5)
        series.append(_night(date, 1 if late else 22, 30, 440))
    r = compute_rhythm(series)
    assert r.social_jetlag_minutes > 90
    assert r.sri < 90


def test_insufficient_data():
    r = compute_rhythm([_night(DATE, 23, 0, 460)])
    assert r.sri is None


def test_rhythm_for_range_demo():
    r = rhythm_for_range(DemoClient(today=DATE), DATE, days=28)
    assert r.sri is not None and 0 <= r.sri <= 100
    assert r.social_jetlag_minutes is not None and r.social_jetlag_minutes > 20  # demo stays up late Fri/Sat


def test_temp_shift_detected_in_synthetic_biphasic_series():
    series = []
    for i in range(28):
        date = str(DATE - dt.timedelta(days=27 - i))
        value = 0.0 if i < 18 else 0.45  # sustained shift in the last 10 days
        series.append({"date": date, "nightly_relative": value})
    rhythm = detect_shifts(series)
    assert len(rhythm.shifts) == 1
    assert rhythm.shifts[0].days >= 3
    assert rhythm.current_state == "elevated"


def test_single_hot_night_is_not_a_shift():
    series = [
        {"date": str(DATE - dt.timedelta(days=27 - i)), "nightly_relative": 0.8 if i == 20 else 0.0}
        for i in range(28)
    ]
    rhythm = detect_shifts(series)
    assert rhythm.shifts == []
    assert rhythm.current_state == "baseline"
