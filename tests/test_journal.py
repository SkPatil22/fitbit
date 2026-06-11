import datetime as dt

from sense2.demo_data import DemoClient
from sense2.journal import Journal, analyze_tag, compare_groups, render_report

DATE = dt.date(2026, 6, 10)


def test_journal_add_remove_list(tmp_path):
    j = Journal(tmp_path / "journal.json")
    j.add(DATE, "alcohol")
    j.add(DATE, "late-meal")
    j.add(DATE - dt.timedelta(days=3), "alcohol")
    assert j.all_tags() == {"alcohol": 2, "late-meal": 1}
    assert j.tags_on(DATE) == ["alcohol", "late-meal"]

    j.remove(DATE, "alcohol")
    assert j.all_tags()["alcohol"] == 1

    # persistence round-trip
    j2 = Journal(tmp_path / "journal.json")
    assert j2.tags_on(DATE) == ["late-meal"]


def test_compare_groups_detects_clear_effect():
    tagged = [30.0, 32.0, 29.0, 31.0, 30.5]  # suppressed HRV
    untagged = [45.0, 46.0, 44.0, 47.0, 45.5, 44.5, 46.5, 45.0]
    effect = compare_groups("hrv_rmssd", tagged, untagged)
    assert effect.delta < -10
    assert effect.verdict == "likely real"


def test_compare_groups_no_effect_on_identical_distributions():
    a = [45.0, 46.0, 44.0, 47.0, 45.5]
    b = [45.2, 45.8, 44.5, 46.5, 45.0, 44.8]
    effect = compare_groups("hrv_rmssd", a, b)
    assert effect.verdict == "no clear effect"


def test_compare_groups_needs_minimum_samples():
    assert compare_groups("hrv_rmssd", [45.0], [44.0, 46.0]) is None


def test_analyze_tag_end_to_end_with_demo(tmp_path):
    j = Journal(tmp_path / "journal.json")
    # tag a handful of demo days; demo data has no systematic alcohol effect,
    # so the pipeline should run and (almost certainly) find nothing dramatic
    for offset in (10, 17, 24, 31, 38):
        j.add(DATE - dt.timedelta(days=offset), "alcohol")
    report = analyze_tag(DemoClient(today=DATE), j, "alcohol", DATE, days=60)
    assert len(report.effects) == 4
    text = render_report(report)
    assert "alcohol" in text and "HRV" in text
