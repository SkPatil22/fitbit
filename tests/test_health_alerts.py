import datetime as dt

from sense2.demo_data import DemoClient
from sense2.health_alerts import evaluate_day, health_check

DATE = dt.date(2026, 6, 10)
STABLE = [58.0, 57.5, 58.5, 59.0, 57.0, 58.0, 58.5, 57.5, 58.0, 58.5]


def test_all_normal_is_ok():
    status = evaluate_day(
        DATE,
        rhr_today=58, rhr_history=STABLE,
        br_today=14.2, br_history=[14.0, 14.3, 14.1, 14.4, 14.2, 14.0, 14.3, 14.1],
        temp_today=0.1, temp_history=[0.0, 0.1, -0.1, 0.2, 0.0, -0.2, 0.1, 0.0],
        hrv_today=45, hrv_history=[44, 46, 45, 43, 47, 45, 44, 46],
    )
    assert status.level == "ok"
    assert status.signals == []


def test_multiple_deviations_trigger_alert():
    status = evaluate_day(
        DATE,
        rhr_today=65, rhr_history=STABLE,  # +7 bpm
        br_today=16.8, br_history=[14.0, 14.3, 14.1, 14.4, 14.2, 14.0, 14.3, 14.1],
        temp_today=1.0, temp_history=[0.0, 0.1, -0.1, 0.2, 0.0, -0.2, 0.1, 0.0],
        hrv_today=30, hrv_history=[44, 46, 45, 43, 47, 45, 44, 46],
    )
    assert status.level == "alert"
    assert len(status.signals) >= 3


def test_single_deviation_is_watch():
    status = evaluate_day(
        DATE,
        rhr_today=65, rhr_history=STABLE,
        br_today=14.2, br_history=[14.0, 14.3, 14.1, 14.4, 14.2, 14.0, 14.3, 14.1],
        temp_today=0.1, temp_history=[0.0, 0.1, -0.1, 0.2, 0.0, -0.2, 0.1, 0.0],
        hrv_today=45, hrv_history=[44, 46, 45, 43, 47, 45, 44, 46],
    )
    assert status.level == "watch"


def test_insufficient_baseline_stays_ok():
    status = evaluate_day(
        DATE,
        rhr_today=70, rhr_history=[58, 59],  # < MIN_BASELINE_DAYS
        br_today=None, br_history=[],
        temp_today=None, temp_history=[],
        hrv_today=None, hrv_history=[],
    )
    assert status.level == "ok"


def test_demo_illness_scenario_triggers_alert():
    # DemoClient elevates RHR/BR/temp and suppresses HRV on `today`.
    status = health_check(DemoClient(today=DATE), DATE)
    assert status.level == "alert"
    metrics = {s.metric for s in status.signals}
    assert "Resting heart rate" in metrics


def test_demo_healthy_day_is_quiet():
    status = health_check(DemoClient(today=DATE, simulate_illness=False), DATE)
    assert status.level in {"ok", "watch"}  # tolerate one noisy metric
