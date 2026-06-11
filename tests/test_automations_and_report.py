import datetime as dt
import json

from sense2.automations import collect_events, deliver
from sense2.demo_data import DemoClient
from sense2.report import gather, generate, render_html

DATE = dt.date(2026, 6, 10)


class FakeResponse:
    def raise_for_status(self):
        pass


def test_collect_events_demo_illness_day():
    events = collect_events(DemoClient(today=DATE), DATE)
    kinds = [e.event for e in events]
    assert "readiness_computed" in kinds
    assert "health_alert" in kinds  # demo simulates illness onset today
    assert "stress_episode" in kinds  # the 11:00 meeting


def test_deliver_posts_once_and_dedupes(tmp_path):
    posted = []

    def fake_post(url, json=None, timeout=None):
        posted.append((url, json))
        return FakeResponse()

    events = collect_events(DemoClient(today=DATE), DATE)
    state = tmp_path / "state.json"

    first = deliver(events, "http://hook.local/x", state_path=state, post=fake_post)
    assert len(first) == len(events) == len(posted)
    assert all(url == "http://hook.local/x" for url, _ in posted)
    assert "event" in posted[0][1] and "payload" in posted[0][1]

    second = deliver(events, "http://hook.local/x", state_path=state, post=fake_post)
    assert second == []  # all deduped
    assert len(posted) == len(events)

    assert len(json.loads(state.read_text())) == len(events)


def test_report_gather_and_render(tmp_path):
    data = gather(DemoClient(today=DATE), DATE, days=21)
    assert data["total_steps"] > 0
    assert data["streak_8k"] >= 0
    assert len(data["steps"]) == 21

    html_text = render_html(data)
    assert "Sense 2 Wrapped" in html_text
    assert "<svg" in html_text  # heatmap rendered
    assert "Training load" in html_text

    out = generate(DemoClient(today=DATE), DATE, 21, tmp_path / "wrapped.html")
    assert out.exists() and out.stat().st_size > 2000
