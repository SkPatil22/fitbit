import datetime as dt
import sqlite3

from sense2.dashboard import create_app
from sense2.demo_data import DemoClient
from sense2.export import export_csv, sync

TODAY = dt.date(2026, 6, 10)


def _app():
    app = create_app(DemoClient(today=TODAY))
    app.testing = True
    return app.test_client()


def test_index_serves_html():
    resp = _app().get("/")
    assert resp.status_code == 200
    assert b"Sense" in resp.data


def test_overview_endpoint():
    resp = _app().get(f"/api/overview?date={TODAY}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["readiness"]["score"] >= 0
    assert data["stress"]["zone_minutes"]
    assert data["health"]["level"] in {"ok", "watch", "alert"}
    assert data["sleep"]["stages"]["deep"] > 0


def test_intraday_endpoint():
    data = _app().get(f"/api/intraday?date={TODAY}").get_json()
    assert len(data["heart"]) == 1440
    assert len(data["stress"]) == 1440


def test_trends_endpoint():
    data = _app().get(f"/api/trends?date={TODAY}&days=14").get_json()
    assert len(data["resting_hr"]) == 14
    assert len(data["hrv"]) == 14


def test_sync_and_export(tmp_path):
    db = tmp_path / "test.db"
    synced = sync(DemoClient(today=TODAY), days=5, db_path=db, end=TODAY,
                  progress=lambda msg: None)
    assert synced == 5
    rows = sqlite3.connect(db).execute("SELECT COUNT(*) FROM daily").fetchone()[0]
    assert rows == 5

    csv_path = tmp_path / "out.csv"
    assert export_csv(db, csv_path) == 5
    header = csv_path.read_text().splitlines()[0]
    assert "readiness" in header and "stress_avg" in header
