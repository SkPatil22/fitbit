import datetime as dt
import sqlite3

from sense2.demo_data import DemoClient
from sense2.server import BackgroundSync

TODAY = dt.date(2026, 6, 10)


def test_background_sync_run_once(tmp_path):
    syncer = BackgroundSync(DemoClient(today=TODAY), tmp_path, interval_min=60)
    summary = syncer.run_once(today=TODAY)

    assert summary["synced_days"] == 3
    assert summary["events_delivered"] == 0  # no webhook configured

    rows = sqlite3.connect(tmp_path / "sense2.db").execute(
        "SELECT COUNT(*) FROM daily"
    ).fetchone()[0]
    assert rows == 3
    assert (tmp_path / "sense2_daily.csv").exists()


def test_background_sync_is_idempotent(tmp_path):
    syncer = BackgroundSync(DemoClient(today=TODAY), tmp_path, interval_min=60)
    syncer.run_once(today=TODAY)
    syncer.run_once(today=TODAY)  # INSERT OR REPLACE — no duplicates
    rows = sqlite3.connect(tmp_path / "sense2.db").execute(
        "SELECT COUNT(*) FROM daily"
    ).fetchone()[0]
    assert rows == 3


def test_background_sync_delivers_webhook_events(tmp_path, monkeypatch):
    posted = []

    class FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, json=None, timeout=None):
        posted.append(url)
        return FakeResponse()

    monkeypatch.setattr("sense2.automations.requests.post", fake_post)
    syncer = BackgroundSync(
        DemoClient(today=TODAY), tmp_path, interval_min=60,
        webhook_url="http://hook.local/x",
    )
    summary = syncer.run_once(today=TODAY)
    assert summary["events_delivered"] == len(posted) > 0
