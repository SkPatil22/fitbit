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


def test_insights_endpoint():
    data = _app().get(f"/api/insights?date={TODAY}&days=14").get_json()
    assert data["training"]["fitness"] >= 0
    assert len(data["training"]["daily"]) == 14
    assert data["rhythm"]["sri"] is not None
    assert data["temperature"]["state"] in {"baseline", "elevated"}
    assert data["sleep_profile"]["animal"]


def test_coach_endpoint_with_injected_session():
    from types import SimpleNamespace

    from sense2.coach import CoachSession
    from sense2.dashboard import create_app

    fake = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                content=[SimpleNamespace(type="text", text="Looking good!")],
                stop_reason="end_turn",
            )
        )
    )
    demo = DemoClient(today=TODAY)
    session = CoachSession(demo, date=TODAY, anthropic_client=fake)
    app = create_app(demo, coach_session=session)
    app.testing = True
    web = app.test_client()

    resp = web.post("/api/coach", json={"message": "How am I doing?"})
    assert resp.status_code == 200
    assert resp.get_json() == {"reply": "Looking good!", "used_specialist": False}

    assert web.post("/api/coach", json={"message": ""}).status_code == 400


def test_coach_endpoint_degrades_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    resp = _app().post("/api/coach", json={"message": "hello"})
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.get_json()["error"]


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
