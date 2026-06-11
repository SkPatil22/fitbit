import datetime as dt

from sense2.demo_data import DemoClient
from sense2.readiness import compute_readiness, readiness_for_date

DATE = dt.date(2026, 6, 10)


def test_well_recovered_scores_high():
    r = compute_readiness(
        DATE,
        hrv_today=50, hrv_baseline=45,
        rhr_today=56, rhr_baseline=58,
        minutes_asleep=470, sleep_efficiency=94,
    )
    assert r.score >= 85
    assert r.label == "Primed"


def test_poor_recovery_scores_low():
    r = compute_readiness(
        DATE,
        hrv_today=28, hrv_baseline=45,
        rhr_today=66, rhr_baseline=58,
        minutes_asleep=300, sleep_efficiency=74,
    )
    assert r.score <= 40
    assert "rest" in r.recommendation.lower()


def test_missing_data_is_neutral():
    r = compute_readiness(DATE, None, None, None, None, None, None)
    assert r.score == 60


def test_readiness_for_date_with_demo_client():
    r = readiness_for_date(DemoClient(today=DATE), DATE)
    assert 0 <= r.score <= 100
    assert r.label in {"Primed", "Good", "Fair", "Run down"}
