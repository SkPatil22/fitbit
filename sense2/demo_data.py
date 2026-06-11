"""Deterministic synthetic Sense 2 data for demo mode and tests.

DemoClient implements the same interface as FitbitClient so the whole stack
(dashboard, CLI, analytics, export) runs without a Fitbit account. Data is
seeded per-date, so repeated calls are stable. The two days before `today`
simulate the onset of an illness (elevated resting HR, breathing rate and
skin temperature, suppressed HRV) to exercise the health-alert engine.
"""

from __future__ import annotations

import datetime as dt
import math
import random


def _rng(date: dt.date, salt: str = "") -> random.Random:
    return random.Random(f"sense2-demo:{date.isoformat()}:{salt}")


class DemoClient:
    def __init__(self, today: dt.date | None = None, simulate_illness: bool = True):
        self.today = today or dt.date.today()
        self.simulate_illness = simulate_illness

    # -- scenario helpers ----------------------------------------------------

    def _illness_factor(self, date: dt.date) -> float:
        """0.0 = healthy, 1.0 = peak pre-symptomatic deviation."""
        if not self.simulate_illness:
            return 0.0
        days_before_today = (self.today - date).days
        return {0: 1.0, 1: 1.0, 2: 0.5}.get(days_before_today, 0.0)

    def _resting_hr(self, date: dt.date) -> int:
        rng = _rng(date, "rhr")
        drift = 2.0 * math.sin(date.toordinal() / 11.0)
        return round(58 + drift + rng.gauss(0, 1.0) + 7 * self._illness_factor(date))

    # -- intraday ------------------------------------------------------------

    def heart_intraday(self, date: dt.date, detail: str = "1min") -> dict:
        rng = _rng(date, "hr")
        rhr = self._resting_hr(date)
        samples = []
        for minute in range(0, 24 * 60):
            t = f"{minute // 60:02d}:{minute % 60:02d}:00"
            if minute < 405:  # asleep until ~06:45
                bpm = rhr - 6 + 3 * math.sin(minute / 90.0) + rng.gauss(0, 2)
            elif 540 <= minute < 585:  # 09:00 commute walk
                bpm = rhr + 30 + rng.gauss(0, 4)
            elif 660 <= minute < 705:  # 11:00 stressful meeting (no movement)
                bpm = rhr + 22 + rng.gauss(0, 3)
            elif 1080 <= minute < 1125:  # 18:00 workout
                bpm = 135 + 15 * math.sin((minute - 1080) / 14.0) + rng.gauss(0, 5)
            elif minute >= 1380:  # 23:00 winding down
                bpm = rhr + 2 + rng.gauss(0, 2)
            else:
                bpm = rhr + 9 + 4 * math.sin(minute / 120.0) + rng.gauss(0, 3)
            samples.append((t, max(40, round(bpm))))
        return {"date": str(date), "resting_hr": rhr, "samples": samples}

    def steps_intraday(self, date: dt.date) -> dict:
        rng = _rng(date, "steps")
        samples = []
        for minute in range(0, 24 * 60):
            t = f"{minute // 60:02d}:{minute % 60:02d}:00"
            if 540 <= minute < 585 or 1080 <= minute < 1125:
                steps = rng.randint(70, 120)  # walk / workout
            elif 405 <= minute < 1380 and rng.random() < 0.15:
                steps = rng.randint(5, 40)  # ambient movement
            else:
                steps = 0
            samples.append((t, steps))
        return {"date": str(date), "samples": samples}

    # -- daily metrics ---------------------------------------------------------

    def hrv_daily(self, date: dt.date) -> dict | None:
        rng = _rng(date, "hrv")
        rmssd = 44 + 4 * math.sin(date.toordinal() / 9.0) + rng.gauss(0, 3)
        rmssd *= 1 - 0.35 * self._illness_factor(date)
        return {"date": str(date), "rmssd": round(rmssd, 1), "deep_rmssd": round(rmssd * 1.15, 1)}

    def sleep_summary(self, date: dt.date) -> dict | None:
        rng = _rng(date, "sleep")
        illness = self._illness_factor(date)
        deep = max(30, round(rng.gauss(88, 12) - 25 * illness))
        light = round(rng.gauss(235, 20))
        rem = max(30, round(rng.gauss(102, 14) - 15 * illness))
        wake = round(rng.gauss(38, 8) + 15 * illness)
        asleep = deep + light + rem

        # Bedtime drifts night to night; Fri/Sat nights run notably later, which
        # gives the sleep-rhythm analytics (social jetlag, SRI) something real.
        prev = date - dt.timedelta(days=1)
        trng = _rng(date, "sleeptime")
        bed_minute = 22 * 60 + 40 + round(trng.gauss(35, 20))
        if prev.weekday() in (4, 5):  # Friday or Saturday night
            bed_minute += round(trng.gauss(75, 25))
        start_dt = dt.datetime.combine(prev, dt.time(0, 0)) + dt.timedelta(minutes=bed_minute)
        end_dt = start_dt + dt.timedelta(minutes=asleep + wake)
        return {
            "date": str(date),
            "start": start_dt.isoformat(timespec="seconds") + ".000",
            "end": end_dt.isoformat(timespec="seconds") + ".000",
            "minutes_asleep": asleep,
            "efficiency": max(70, min(98, round(100 * asleep / (asleep + wake)))),
            "stages": {"deep": deep, "light": light, "rem": rem, "wake": wake},
        }

    def spo2(self, date: dt.date) -> dict | None:
        rng = _rng(date, "spo2")
        avg = round(rng.gauss(96.8, 0.5) - 0.8 * self._illness_factor(date), 1)
        return {"avg": avg, "min": round(avg - rng.uniform(1.5, 3.0), 1), "max": round(avg + 1.4, 1)}

    def breathing_rate(self, date: dt.date) -> dict | None:
        rng = _rng(date, "br")
        return {"rate": round(rng.gauss(14.2, 0.5) + 2.2 * self._illness_factor(date), 1)}

    def skin_temp(self, date: dt.date) -> dict | None:
        rng = _rng(date, "temp")
        return {
            "nightly_relative": round(rng.gauss(0.0, 0.25) + 0.9 * self._illness_factor(date), 2)
        }

    def cardio_score(self, date: dt.date) -> dict | None:
        return {"vo2max": "42-46"}

    def ecg_readings(self, limit: int = 10) -> list[dict]:
        return [
            {
                "start": f"{self.today - dt.timedelta(days=7)}T08:12:00",
                "classification": "NORMAL_SINUS_RHYTHM",
                "avg_hr": 61,
            }
        ][:limit]

    def profile(self) -> dict:
        return {"name": "Demo User", "age": 32}

    # -- trend series ----------------------------------------------------------

    def _dates(self, start: dt.date, end: dt.date):
        d = start
        while d <= end:
            yield d
            d += dt.timedelta(days=1)

    def resting_hr_series(self, start: dt.date, end: dt.date) -> list[dict]:
        return [{"date": str(d), "resting_hr": self._resting_hr(d)} for d in self._dates(start, end)]

    def hrv_series(self, start: dt.date, end: dt.date) -> list[dict]:
        return [
            {"date": str(d), "rmssd": self.hrv_daily(d)["rmssd"]} for d in self._dates(start, end)
        ]

    def breathing_rate_series(self, start: dt.date, end: dt.date) -> list[dict]:
        return [
            {"date": str(d), "rate": self.breathing_rate(d)["rate"]}
            for d in self._dates(start, end)
        ]

    def skin_temp_series(self, start: dt.date, end: dt.date) -> list[dict]:
        return [
            {"date": str(d), "nightly_relative": self.skin_temp(d)["nightly_relative"]}
            for d in self._dates(start, end)
        ]

    def steps_series(self, start: dt.date, end: dt.date) -> list[dict]:
        out = []
        for d in self._dates(start, end):
            rng = _rng(d, "daysteps")
            base = 9500 if d.weekday() >= 5 else 8200  # longer weekend walks
            steps = max(
                500,
                round(rng.gauss(base, 2200) * (1 - 0.45 * self._illness_factor(d))),
            )
            out.append({"date": str(d), "steps": steps})
        return out

    def azm_series(self, start: dt.date, end: dt.date) -> list[dict]:
        out = []
        for d in self._dates(start, end):
            rng = _rng(d, "azm")
            azm = max(0, round(rng.gauss(45, 18) * (1 - 0.6 * self._illness_factor(d))))
            out.append({"date": str(d), "azm": azm})
        return out

    def sleep_series(self, start: dt.date, end: dt.date) -> list[dict]:
        out = []
        for d in self._dates(start, end):
            s = self.sleep_summary(d)
            out.append(
                {
                    "date": str(d),
                    "minutes_asleep": s["minutes_asleep"],
                    "efficiency": s["efficiency"],
                    "start": s["start"],
                    "end": s["end"],
                }
            )
        return out
