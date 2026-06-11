"""Fitbit Web API client covering every data type the Sense 2 records.

All methods return normalized plain dicts/lists so the analytics modules
(stress, readiness, health_alerts) and the demo client share one interface:

    heart_intraday(date)   -> {"date", "resting_hr", "samples": [(HH:MM:SS, bpm)]}
    steps_intraday(date)   -> {"date", "samples": [(HH:MM:SS, steps)]}
    hrv_daily(date)        -> {"date", "rmssd", "deep_rmssd"} | None
    sleep_summary(date)    -> {"minutes_asleep", "efficiency", "stages", ...} | None
    spo2(date)             -> {"avg", "min", "max"} | None
    breathing_rate(date)   -> {"rate"} | None
    skin_temp(date)        -> {"nightly_relative"} | None
    *_series(start, end)   -> [{"date", <value>}, ...] daily trend series
"""

from __future__ import annotations

import datetime as dt

import requests

from .auth import TokenStore

API = "https://api.fitbit.com"


class RateLimitError(Exception):
    """Fitbit allows 150 requests/hour per user; raised on HTTP 429."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Fitbit rate limit hit — retry in {retry_after}s")


class FitbitClient:
    def __init__(self, store: TokenStore):
        self.store = store

    # -- transport ---------------------------------------------------------

    def _get(self, path: str) -> dict:
        resp = requests.get(
            f"{API}{path}",
            headers={"Authorization": f"Bearer {self.store.access_token()}"},
            timeout=30,
        )
        if resp.status_code == 429:
            raise RateLimitError(int(resp.headers.get("Retry-After", "3600")))
        resp.raise_for_status()
        return resp.json()

    # -- intraday ----------------------------------------------------------

    def heart_intraday(self, date: dt.date, detail: str = "1min") -> dict:
        data = self._get(f"/1/user/-/activities/heart/date/{date}/1d/{detail}.json")
        day = (data.get("activities-heart") or [{}])[0]
        return {
            "date": str(date),
            "resting_hr": day.get("value", {}).get("restingHeartRate"),
            "samples": [
                (p["time"], p["value"])
                for p in data.get("activities-heart-intraday", {}).get("dataset", [])
            ],
        }

    def steps_intraday(self, date: dt.date) -> dict:
        data = self._get(f"/1/user/-/activities/steps/date/{date}/1d/1min.json")
        return {
            "date": str(date),
            "samples": [
                (p["time"], p["value"])
                for p in data.get("activities-steps-intraday", {}).get("dataset", [])
            ],
        }

    # -- daily health metrics ----------------------------------------------

    def hrv_daily(self, date: dt.date) -> dict | None:
        entries = self._get(f"/1/user/-/hrv/date/{date}.json").get("hrv", [])
        if not entries:
            return None
        value = entries[0].get("value", {})
        return {
            "date": str(date),
            "rmssd": value.get("dailyRmssd"),
            "deep_rmssd": value.get("deepRmssd"),
        }

    def sleep_summary(self, date: dt.date) -> dict | None:
        data = self._get(f"/1.2/user/-/sleep/date/{date}.json")
        main = next((s for s in data.get("sleep", []) if s.get("isMainSleep")), None)
        if not main:
            return None
        stages = main.get("levels", {}).get("summary", {})
        return {
            "date": str(date),
            "start": main.get("startTime"),
            "end": main.get("endTime"),
            "minutes_asleep": main.get("minutesAsleep"),
            "efficiency": main.get("efficiency"),
            "stages": {
                k: stages.get(k, {}).get("minutes", 0)
                for k in ("deep", "light", "rem", "wake")
            },
        }

    def spo2(self, date: dt.date) -> dict | None:
        value = self._get(f"/1/user/-/spo2/date/{date}.json").get("value")
        if not value:
            return None
        return {"avg": value.get("avg"), "min": value.get("min"), "max": value.get("max")}

    def breathing_rate(self, date: dt.date) -> dict | None:
        entries = self._get(f"/1/user/-/br/date/{date}.json").get("br", [])
        if not entries:
            return None
        return {"rate": entries[0].get("value", {}).get("breathingRate")}

    def skin_temp(self, date: dt.date) -> dict | None:
        entries = self._get(f"/1/user/-/temp/skin/date/{date}.json").get("tempSkin", [])
        if not entries:
            return None
        return {"nightly_relative": entries[0].get("value", {}).get("nightlyRelative")}

    def cardio_score(self, date: dt.date) -> dict | None:
        entries = self._get(f"/1/user/-/cardioscore/date/{date}.json").get("cardioScore", [])
        if not entries:
            return None
        return {"vo2max": entries[0].get("value", {}).get("vo2Max")}

    def ecg_readings(self, limit: int = 10) -> list[dict]:
        data = self._get(
            f"/1/user/-/ecg/list.json?sort=desc&limit={limit}&offset=0"
        )
        return [
            {
                "start": r.get("startTime"),
                "classification": r.get("resultClassification"),
                "avg_hr": r.get("averageHeartRate"),
            }
            for r in data.get("ecgReadings", [])
        ]

    def profile(self) -> dict:
        user = self._get("/1/user/-/profile.json").get("user", {})
        return {"name": user.get("displayName"), "age": user.get("age")}

    # -- trend series --------------------------------------------------------

    def resting_hr_series(self, start: dt.date, end: dt.date) -> list[dict]:
        data = self._get(f"/1/user/-/activities/heart/date/{start}/{end}.json")
        return [
            {"date": d["dateTime"], "resting_hr": d.get("value", {}).get("restingHeartRate")}
            for d in data.get("activities-heart", [])
            if d.get("value", {}).get("restingHeartRate") is not None
        ]

    def hrv_series(self, start: dt.date, end: dt.date) -> list[dict]:
        data = self._get(f"/1/user/-/hrv/date/{start}/{end}.json")
        return [
            {"date": d["dateTime"], "rmssd": d.get("value", {}).get("dailyRmssd")}
            for d in data.get("hrv", [])
            if d.get("value", {}).get("dailyRmssd") is not None
        ]

    def breathing_rate_series(self, start: dt.date, end: dt.date) -> list[dict]:
        data = self._get(f"/1/user/-/br/date/{start}/{end}.json")
        return [
            {"date": d["dateTime"], "rate": d.get("value", {}).get("breathingRate")}
            for d in data.get("br", [])
            if d.get("value", {}).get("breathingRate") is not None
        ]

    def skin_temp_series(self, start: dt.date, end: dt.date) -> list[dict]:
        data = self._get(f"/1/user/-/temp/skin/date/{start}/{end}.json")
        return [
            {"date": d["dateTime"], "nightly_relative": d.get("value", {}).get("nightlyRelative")}
            for d in data.get("tempSkin", [])
            if d.get("value", {}).get("nightlyRelative") is not None
        ]

    def steps_series(self, start: dt.date, end: dt.date) -> list[dict]:
        data = self._get(f"/1/user/-/activities/steps/date/{start}/{end}.json")
        return [
            {"date": d["dateTime"], "steps": int(d["value"])}
            for d in data.get("activities-steps", [])
        ]

    def azm_series(self, start: dt.date, end: dt.date) -> list[dict]:
        data = self._get(
            f"/1/user/-/activities/active-zone-minutes/date/{start}/{end}.json"
        )
        return [
            {
                "date": d["dateTime"],
                "azm": d.get("value", {}).get("activeZoneMinutes", 0),
            }
            for d in data.get("activities-active-zone-minutes", [])
        ]

    def sleep_series(self, start: dt.date, end: dt.date) -> list[dict]:
        data = self._get(f"/1.2/user/-/sleep/date/{start}/{end}.json")
        out = []
        for s in data.get("sleep", []):
            if s.get("isMainSleep"):
                out.append(
                    {
                        "date": s.get("dateOfSleep"),
                        "minutes_asleep": s.get("minutesAsleep"),
                        "efficiency": s.get("efficiency"),
                        "start": s.get("startTime"),
                        "end": s.get("endTime"),
                    }
                )
        return sorted(out, key=lambda d: d["date"])
