"""Always-on local server: dashboard + periodic background sync.

`python -m sense2 server` (or just `sense2 server` once installed) serves the
dashboard with waitress (a production WSGI server that runs fine on a
Raspberry Pi) and runs a background thread that periodically:

  * syncs recent days into the local SQLite archive, and
  * pushes new events (readiness, alerts, stress episodes, goals) to a
    webhook if one is configured.

Designed to run forever under systemd — sync errors (rate limits, network
blips, expired tokens) are logged and retried on the next cycle, never fatal.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from pathlib import Path

from . import export as export_mod
from .automations import collect_events, deliver
from .dashboard import create_app

log = logging.getLogger("sense2.server")

DEFAULT_PORT = 8400
SYNC_DAYS = 3  # re-sync a few trailing days each cycle (late-arriving data)


class BackgroundSync(threading.Thread):
    def __init__(self, client, data_dir: Path, interval_min: int,
                 webhook_url: str | None = None, days: int = SYNC_DAYS):
        super().__init__(daemon=True, name="sense2-sync")
        self.client = client
        self.data_dir = Path(data_dir)
        self.interval_min = interval_min
        self.webhook_url = webhook_url
        self.days = days
        self._stop = threading.Event()

    def run_once(self, today: dt.date | None = None) -> dict:
        """One sync cycle; returns a small summary for logging/tests."""
        today = today or dt.date.today()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        db_path = self.data_dir / "sense2.db"
        synced = export_mod.sync(
            self.client, self.days, db_path, end=today, progress=log.debug
        )
        export_mod.export_csv(db_path, self.data_dir / "sense2_daily.csv")

        delivered = 0
        if self.webhook_url:
            events = collect_events(self.client, today)
            delivered = len(
                deliver(events, self.webhook_url,
                        state_path=self.data_dir / "webhook_state.json")
            )
        return {"synced_days": synced, "events_delivered": delivered}

    def run(self):
        while not self._stop.is_set():
            try:
                summary = self.run_once()
                log.info("sync ok: %s", summary)
            except Exception as exc:  # never kill the loop — retry next cycle
                log.warning("sync failed (will retry in %dmin): %s",
                            self.interval_min, exc)
            self._stop.wait(self.interval_min * 60)

    def stop(self):
        self._stop.set()


def serve(client, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
          sync_interval_min: int = 60, webhook_url: str | None = None,
          data_dir: Path | None = None) -> None:
    """Run the dashboard + background sync until killed."""
    app = create_app(client)
    data_dir = Path(data_dir or Path.home() / ".sense2")

    syncer = None
    if sync_interval_min > 0:
        syncer = BackgroundSync(client, data_dir, sync_interval_min, webhook_url)
        syncer.start()
        log.info("background sync every %dmin -> %s", sync_interval_min, data_dir)

    log.info("dashboard listening on http://%s:%d", host, port)
    try:
        from waitress import serve as waitress_serve

        waitress_serve(app, host=host, port=port, threads=8)
    except ImportError:
        log.warning("waitress not installed — falling back to Flask dev server")
        app.run(host=host, port=port)
    finally:
        if syncer:
            syncer.stop()
