import datetime as dt

import pytest

from sense2.demo_data import DemoClient
from sense2.sessions import analyze_session, render_card

DATE = dt.date(2026, 6, 10)


def test_meeting_window_shows_elevated_hr_and_stress():
    # the demo day has a stressful 11:00-11:45 meeting (HR +22, no steps)
    result = analyze_session(DemoClient(today=DATE), DATE, "10:30", "12:00", "Standup")
    assert result.avg_hr > result.resting_hr
    assert result.max_hr >= result.resting_hr + 15
    assert result.avg_stress > 20
    assert 1 <= len(result.peaks) <= 3
    assert all("10:30" <= p.time < "12:00" for p in result.peaks)


def test_workout_window_is_flagged_active_not_stressed():
    result = analyze_session(DemoClient(today=DATE), DATE, "18:00", "18:45", "Run")
    assert result.active_minutes >= 40
    assert result.max_hr > 120


def test_empty_window_raises():
    client = DemoClient(today=DATE)
    with pytest.raises(ValueError):
        analyze_session(client, DATE, "25:00", "26:00", "nope")


def test_render_card_contains_essentials():
    result = analyze_session(DemoClient(today=DATE), DATE, "21:00", "22:30", "Hereditary")
    card = render_card(result)
    assert "Hereditary" in card
    assert "avg" in card and "peak" in card
    assert str(result.max_hr) in card
