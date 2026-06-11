"""Flask dashboard serving the Sense 2 companion UI and JSON API."""

from __future__ import annotations

import datetime as dt

from flask import Flask, jsonify, render_template, request

from ..coach import CoachError, CoachSession
from ..health_alerts import health_check
from ..readiness import readiness_for_date
from ..sleep_profile import profile_for_range
from ..sleep_rhythm import rhythm_for_range
from ..stress import stress_for_date
from ..temp_rhythm import detect_shifts
from ..training import training_for_range


def create_app(client, coach_session: CoachSession | None = None) -> Flask:
    app = Flask(__name__)
    app.config["CLIENT"] = client
    app.config["COACH"] = coach_session

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

    @app.route("/api/insights")
    def insights():
        date = _date()
        days = int(request.args.get("days", 28))
        training = training_for_range(client, date, days=days)
        rhythm = rhythm_for_range(client, date, days=days)
        temp = detect_shifts(
            client.skin_temp_series(date - dt.timedelta(days=days - 1), date)
        )
        return jsonify(
            {
                "training": {
                    "fitness": training.fitness,
                    "fatigue": training.fatigue,
                    "form": training.form,
                    "label": training.label,
                    "advice": training.advice,
                    "weekly_trimp": training.weekly_trimp,
                    "daily": [
                        {"date": d.date, "trimp": d.trimp} for d in training.days
                    ],
                },
                "rhythm": {
                    "sri": rhythm.sri,
                    "social_jetlag_minutes": rhythm.social_jetlag_minutes,
                    "avg_midpoint": rhythm.avg_midpoint,
                    "debt_minutes": rhythm.debt_minutes,
                    "summary": rhythm.summary,
                },
                "temperature": {
                    "state": temp.current_state,
                    "summary": temp.summary,
                    "shifts": [vars(s) for s in temp.shifts],
                },
                "sleep_profile": (
                    vars(sleep_profile)
                    if (sleep_profile := profile_for_range(client, date)) else None
                ),
            }
        )

    @app.route("/api/coach", methods=["POST"])
    def coach():
        payload = request.get_json(silent=True) or {}
        message = (payload.get("message") or "").strip()
        if not message:
            return jsonify({"error": "empty message"}), 400
        if app.config["COACH"] is None:
            app.config["COACH"] = CoachSession(client)
        try:
            reply = app.config["COACH"].ask(message)
        except CoachError as exc:
            return jsonify({"error": str(exc)}), 503
        return jsonify(
            {"reply": reply.text, "used_specialist": reply.used_specialist}
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
