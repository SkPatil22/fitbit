"""Local archive of Sense 2 data: SQLite sync + CSV export.

Fitbit only exposes the trailing window of fine-grained data conveniently, and
the API is rate-limited to 150 requests/hour — so people archive their own
copy. `sync` pulls daily metrics (plus computed stress/readiness) into SQLite;
`export_csv` dumps the table for spreadsheets/notebooks.
"""

from __future__ import annotations

import csv
import datetime as dt
import sqlite3
from pathlib import Path

from .readiness import readiness_for_date
from .stress import stress_for_date

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily (
    date TEXT PRIMARY KEY,
    resting_hr INTEGER,
    hrv_rmssd REAL,
    breathing_rate REAL,
    spo2_avg REAL,
    skin_temp_rel REAL,
    sleep_minutes INTEGER,
    sleep_efficiency INTEGER,
    stress_avg INTEGER,
    stress_peak INTEGER,
    readiness INTEGER
);
"""

COLUMNS = [
    "date", "resting_hr", "hrv_rmssd", "breathing_rate", "spo2_avg",
    "skin_temp_rel", "sleep_minutes", "sleep_efficiency", "stress_avg",
    "stress_peak", "readiness",
]


def sync(client, days: int, db_path: Path, end: dt.date | None = None,
         progress=print) -> int:
    """Pull `days` days ending at `end` (default today) into SQLite."""
    end = end or dt.date.today()
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    synced = 0
    for offset in range(days):
        date = end - dt.timedelta(days=offset)
        heart = client.heart_intraday(date)
        hrv = client.hrv_daily(date)
        br = client.breathing_rate(date)
        spo2 = client.spo2(date)
        temp = client.skin_temp(date)
        sleep = client.sleep_summary(date)
        stress = stress_for_date(client, date)
        readiness = readiness_for_date(client, date)
        conn.execute(
            f"INSERT OR REPLACE INTO daily ({','.join(COLUMNS)}) "
            f"VALUES ({','.join('?' * len(COLUMNS))})",
            (
                str(date),
                heart.get("resting_hr"),
                hrv["rmssd"] if hrv else None,
                br["rate"] if br else None,
                spo2["avg"] if spo2 else None,
                temp["nightly_relative"] if temp else None,
                sleep["minutes_asleep"] if sleep else None,
                sleep["efficiency"] if sleep else None,
                stress.daily_avg,
                stress.peak,
                readiness.score,
            ),
        )
        synced += 1
        progress(f"  synced {date}")
    conn.commit()
    conn.close()
    return synced


def export_csv(db_path: Path, out_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        f"SELECT {','.join(COLUMNS)} FROM daily ORDER BY date"
    ).fetchall()
    conn.close()
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return len(rows)
