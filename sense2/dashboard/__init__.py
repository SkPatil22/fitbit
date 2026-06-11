"""Flask dashboard serving the Sense 2 companion UI and JSON API."""

from __future__ import annotations

import datetime as dt

from flask import Flask, jsonify, render_template, request

from ..health_alerts import health_check
from ..readiness import readiness_for_date
from ..stress import stress_for_date


def create_app(client) -> Flask:
    app = Flask(__name__)
    app.config["CLIENT"] = client

    def _date() -> dt.date:
        raw = request.args.get("date")
        return dt.date.fromisoformat(raw) if raw else dt.date.today()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/overview")
    def overview():
        date = _date()
        readiness = readiness_for_date(client, date)
        stress = stress_for_date(client, date)
        health = health_check(client, date)
        sleep = client.sleep_summary(date)
        return jsonify(
            {
                "date": str(date),
                "profile": client.profile(),
                "readiness": vars(readiness),
                "stress": {
                    "daily_avg": stress.daily_avg,
                    "peak": stress.peak,
                    "zone_minutes": stress.zone_minutes,
                    "hrv_modifier": stress.hrv_modifier,
                    "episodes": [vars(e) for e in stress.episodes],
                },
                "health": {
                    "level": health.level,
                    "summary": health.summary,
                    "signals": [vars(s) for s in health.signals],
                },
                "sleep": sleep,
                "spo2": client.spo2(date),
                "breathing_rate": client.breathing_rate(date),
                "skin_temp": client.skin_temp(date),
                "hrv": client.hrv_daily(date),
                "resting_hr": client.heart_intraday(date)["resting_hr"],
            }
        )

    @app.route("/api/intraday")
    def intraday():
        date = _date()
        heart = client.heart_intraday(date)
        stress = stress_for_date(client, date)
        return jsonify(
            {
                "date": str(date),
                "heart": heart["samples"],
                "resting_hr": heart["resting_hr"],
                "stress": stress.samples,
            }
        )

    @app.route("/api/trends")
    def trends():
        days = int(request.args.get("days", 30))
        end = _date()
        start = end - dt.timedelta(days=days - 1)
        return jsonify(
            {
                "resting_hr": client.resting_hr_series(start, end),
                "hrv": client.hrv_series(start, end),
                "breathing_rate": client.breathing_rate_series(start, end),
                "skin_temp": client.skin_temp_series(start, end),
                "sleep": client.sleep_series(start, end),
            }
        )

    return app
