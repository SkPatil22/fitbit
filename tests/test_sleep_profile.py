import datetime as dt

from sense2.demo_data import DemoClient
from sense2.sleep_profile import ANIMALS, compute_profile, profile_for_range

DATE = dt.date(2026, 6, 10)


def _night(date, bed_h, bed_m, asleep, deep, rem, efficiency=93):
    prev = date - dt.timedelta(days=1)
    start = dt.datetime.combine(prev, dt.time(0, 0)) + dt.timedelta(
        minutes=bed_h * 60 + bed_m
    )
    end = start + dt.timedelta(minutes=asleep + 30)
    return {
        "date": str(date),
        "start": start.isoformat() + ".000",
        "end": end.isoformat() + ".000",
        "minutes_asleep": asleep,
        "efficiency": efficiency,
        "stages": {"deep": deep, "light": asleep - deep - rem, "rem": rem, "wake": 30},
    }


def _series(**kwargs):
    return [_night(DATE - dt.timedelta(days=27 - i), **kwargs) for i in range(28)]


def test_long_consistent_deep_sleeper_is_bear():
    profile = compute_profile(_series(bed_h=22, bed_m=50, asleep=470, deep=95, rem=100))
    assert profile.animal == "bear"
    assert profile.avg_duration_min == 470


def test_short_sleeper_is_giraffe():
    profile = compute_profile(_series(bed_h=23, bed_m=30, asleep=350, deep=60, rem=75))
    assert profile.animal == "giraffe"


def test_late_short_sleeper_is_hedgehog():
    # bed at 02:30, asleep 350 min -> midpoint well past 4 AM
    profile = compute_profile(_series(bed_h=26, bed_m=30, asleep=350, deep=60, rem=75))
    assert profile.animal == "hedgehog"


def test_irregular_inefficient_sleeper_is_dolphin():
    series = []
    for i in range(28):
        bed_h = 22 + (i * 5) % 6  # bedtime swings across 5 hours
        series.append(
            _night(DATE - dt.timedelta(days=27 - i), bed_h=bed_h, bed_m=0,
                   asleep=400, deep=55, rem=80, efficiency=84)
        )
    profile = compute_profile(series)
    assert profile.animal == "dolphin"
    assert profile.midpoint_std_min > 75


def test_insufficient_nights_returns_none():
    assert compute_profile(_series(bed_h=23, bed_m=0, asleep=420, deep=80, rem=90)[:5]) is None


def test_demo_client_gets_a_valid_profile():
    profile = profile_for_range(DemoClient(today=DATE), DATE)
    assert profile is not None
    assert profile.animal in ANIMALS
    assert profile.nights >= 10
    assert 0 < profile.deep_pct < 50
