"""Command-line interface for the Sense 2 companion suite.

    python -m sense2 auth                     # one-time OAuth (real device)
    python -m sense2 dashboard [--demo]       # web dashboard at :5000
    python -m sense2 stress    [--demo] [--date YYYY-MM-DD]
    python -m sense2 readiness [--demo] [--date YYYY-MM-DD]
    python -m sense2 alerts    [--demo] [--date YYYY-MM-DD]
    python -m sense2 export    [--demo] [--days N] [--out DIR]
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

from . import export as export_mod
from .health_alerts import health_check
from .readiness import readiness_for_date
from .stress import ZONES, stress_for_date

BAR_BLOCKS = " ▁▂▃▄▅▆▇█"


def _client(args):
    if args.demo:
        from .demo_data import DemoClient

        return DemoClient(today=args.date or dt.date.today())
    from .auth import store_from_env
    from .client import FitbitClient

    return FitbitClient(store_from_env())


def _spark(values: list[float], width: int = 60) -> str:
    if not values:
        return ""
    step = max(len(values) // width, 1)
    sampled = [values[i] for i in range(0, len(values), step)]
    lo, hi = min(sampled), max(sampled)
    span = (hi - lo) or 1
    return "".join(BAR_BLOCKS[1 + round((v - lo) / span * 7)] for v in sampled)


def cmd_auth(args):
    client_id = os.environ.get("FITBIT_CLIENT_ID") or input("Fitbit client ID: ").strip()
    client_secret = os.environ.get("FITBIT_CLIENT_SECRET", "")
    from .auth import authorize

    authorize(client_id, client_secret)


def cmd_dashboard(args):
    from .dashboard import create_app

    create_app(_client(args)).run(host="127.0.0.1", port=args.port, debug=False)


def cmd_stress(args):
    date = args.date or dt.date.today()
    result = stress_for_date(_client(args), date)
    print(f"\nStress — {result.date}")
    print(f"  daily avg {result.daily_avg}/100, peak {result.peak}/100 "
          f"(HRV modifier ×{result.hrv_modifier})")
    print(f"  {_spark([s for _, s, _ in result.samples])}")
    print("  " + " | ".join(f"{name} {result.zone_minutes[name]}m" for name, *_ in ZONES))
    if result.episodes:
        print("  episodes:")
        for e in result.episodes:
            print(f"    ⚡ {e.start}–{e.end}  avg {e.avg}, peak {e.peak}")
    else:
        print("  no sustained stress episodes")


def cmd_readiness(args):
    date = args.date or dt.date.today()
    r = readiness_for_date(_client(args), date)
    print(f"\nReadiness — {r.date}:  {r.score}/100  [{r.label}]")
    print(f"  HRV {r.hrv_score} · resting HR {r.rhr_score} · sleep {r.sleep_score}")
    print(f"  {r.recommendation}")


def cmd_alerts(args):
    date = args.date or dt.date.today()
    status = health_check(_client(args), date)
    icon = {"ok": "✓", "watch": "⚠", "alert": "✗"}[status.level]
    print(f"\nHealth check — {status.date}:  {icon} {status.level.upper()}")
    print(f"  {status.summary}")
    for s in status.signals:
        print(f"  • {s.message}")


def cmd_export(args):
    client = _client(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    db = out / "sense2.db"
    print(f"Syncing {args.days} days into {db} ...")
    export_mod.sync(client, args.days, db, end=args.date or dt.date.today())
    csv_path = out / "sense2_daily.csv"
    rows = export_mod.export_csv(db, csv_path)
    print(f"Exported {rows} rows to {csv_path}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="sense2", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, fn, **extra):
        p = sub.add_parser(name)
        p.add_argument("--demo", action="store_true", help="use synthetic demo data")
        p.add_argument("--date", type=dt.date.fromisoformat, default=None)
        for flag, kwargs in extra.items():
            p.add_argument(flag, **kwargs)
        p.set_defaults(fn=fn)

    add("auth", cmd_auth)
    add("dashboard", cmd_dashboard, **{"--port": {"type": int, "default": 5000}})
    add("stress", cmd_stress)
    add("readiness", cmd_readiness)
    add("alerts", cmd_alerts)
    add(
        "export",
        cmd_export,
        **{
            "--days": {"type": int, "default": 30},
            "--out": {"default": "./sense2_export"},
        },
    )

    args = parser.parse_args(argv)
    try:
        args.fn(args)
    except Exception as exc:  # surface a clean message instead of a traceback
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
