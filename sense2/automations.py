"""Webhook bridge: push Sense 2 events into Home Assistant / n8n / IFTTT.

The Fitbit API has no push, so r/homeassistant folks poll and forward. This
module computes the day's interesting events and POSTs each one as JSON to a
webhook URL — the universal trigger format all automation platforms accept:

    {"event": "health_alert", "date": "2026-06-10", "payload": {...}}

Events: readiness_computed (always), health_alert (watch/alert only),
stress_episode (each sustained episode), goal_hit (steps >= goal). A state
file remembers what was already sent so re-running (cron-friendly) never
duplicates an event.

    python -m sense2 webhook --url https://homeassistant.local:8123/api/webhook/sense2
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import requests

from .health_alerts import health_check
from .readiness import readiness_for_date
from .stress import stress_for_date

DEFAULT_STATE_PATH = Path.home() / ".sense2" / "webhook_state.json"
STEPS_GOAL = 10_000


@dataclass
class Event:
    event: str
    date: str
    payload: dict

    @property
    def key(self) -> str:
        suffix = self.payload.get("start", "")
        return f"{self.date}:{self.event}:{suffix}"


def collect_events(client, date: dt.date, steps_goal: int = STEPS_GOAL) -> list[Event]:
    events = []

    readiness = readiness_for_date(client, date)
    events.append(
        Event("readiness_computed", str(date), {
            "score": readiness.score,
            "label": readiness.label,
            "recommendation": readiness.recommendation,
        })
    )

    health = health_check(client, date)
    if health.level != "ok":
        events.append(
            Event("health_alert", str(date), {
                "level": health.level,
                "summary": health.summary,
                "signals": [s.message for s in health.signals],
            })
        )

    stress = stress_for_date(client, date)
    for episode in stress.episodes:
        events.append(
            Event("stress_episode", str(date), {
                "start": episode.start,
                "end": episode.end,
                "peak": episode.peak,
                "avg": episode.avg,
            })
        )

    steps_today = client.steps_series(date, date)
    if steps_today and steps_today[0]["steps"] >= steps_goal:
        events.append(
            Event("goal_hit", str(date), {"steps": steps_today[0]["steps"], "goal": steps_goal})
        )
    return events


def deliver(events: list[Event], url: str, state_path: Path | None = None,
            post=requests.post) -> list[Event]:
    """POST events not yet recorded in the state file; returns those sent."""
    state_path = Path(state_path or DEFAULT_STATE_PATH)
    sent: set[str] = set(json.loads(state_path.read_text())) if state_path.exists() else set()

    delivered = []
    for event in events:
        if event.key in sent:
            continue
        resp = post(url, json={"event": event.event, "date": event.date,
                               "payload": event.payload}, timeout=15)
        resp.raise_for_status()
        sent.add(event.key)
        delivered.append(event)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(sorted(sent), indent=2))
    return delivered
