"""Command-line interface for the Sense 2 companion suite.

    python -m sense2 auth                     # one-time OAuth (real device)
    python -m sense2 dashboard [--demo]       # web dashboard at :5000
    python -m sense2 stress    [--demo] [--date YYYY-MM-DD]
    python -m sense2 readiness [--demo] [--date YYYY-MM-DD]
    python -m sense2 alerts    [--demo] [--date YYYY-MM-DD]
    python -m sense2 export    [--demo] [--days N] [--out DIR]
    python -m sense2 session   [--demo] --from HH:MM --to HH:MM --label "..."
    python -m sense2 training  [--demo] [--days N]
    python -m sense2 rhythm    [--demo] [--days N]
    python -m sense2 report    [--demo] [--days N] [--out FILE.html]
    python -m sense2 journal   add|remove|list|analyze ...
    python -m sense2 webhook   --url URL [--demo]
    python -m sense2 profile   [--demo] [--days N]      # monthly sleep animal
    python -m sense2 coach     [--demo] ["question"]    # AI coach (needs ANTHROPIC_API_KEY)
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


def cmd_session(args):
    from .sessions import analyze_session, render_card

    date = args.date or dt.date.today()
    result = analyze_session(_client(args), date, args.start, args.end, args.label)
    print("\n" + render_card(result))


def cmd_training(args):
    from .training import training_for_range

    status = training_for_range(_client(args), args.date or dt.date.today(), days=args.days)
    print(f"\nTraining load over {args.days} days (Banister TRIMP):")
    print(f"  fitness (CTL) {status.fitness} · fatigue (ATL) {status.fatigue} · "
          f"form (TSB) {status.form:+}  [{status.label}]")
    print(f"  last 7 days: {status.weekly_trimp} TRIMP")
    print(f"  {_spark([d.trimp for d in status.days])}")
    today = status.days[-1]
    zones = " | ".join(f"{k} {v}m" for k, v in today.zone_minutes.items() if v)
    print(f"  today: {today.trimp} TRIMP ({zones or 'rest day'})")
    print(f"  {status.advice}")


def cmd_rhythm(args):
    from .sleep_rhythm import rhythm_for_range
    from .temp_rhythm import detect_shifts

    end = args.date or dt.date.today()
    rhythm = rhythm_for_range(_client(args), end, days=args.days)
    print(f"\nSleep rhythm ({args.days} days): {rhythm.summary}")
    print(f"  avg sleep midpoint {rhythm.avg_midpoint} over {rhythm.nights} nights")
    temp = detect_shifts(
        _client(args).skin_temp_series(end - dt.timedelta(days=args.days - 1), end)
    )
    print(f"Temperature: {temp.summary}")


def cmd_report(args):
    from .report import generate

    out = generate(_client(args), args.date or dt.date.today(), args.days, Path(args.out))
    print(f"Report written to {out}")


def cmd_journal(args):
    from .journal import Journal, analyze_tag, render_report

    journal = Journal(Path(args.journal) if args.journal else None)
    if args.action == "add":
        journal.add(args.date or dt.date.today(), args.tag)
        print(f"Tagged {args.date or dt.date.today()} with '{args.tag}'.")
    elif args.action == "remove":
        journal.remove(args.date or dt.date.today(), args.tag)
        print(f"Removed '{args.tag}' from {args.date or dt.date.today()}.")
    elif args.action == "list":
        counts = journal.all_tags()
        if not counts:
            print("Journal is empty. Tag days with: python -m sense2 journal add <tag> --date ...")
        for tag, n in counts.items():
            print(f"  {tag}: {n} day(s)")
    elif args.action == "analyze":
        report = analyze_tag(
            _client(args), journal, args.tag, args.date or dt.date.today(), days=args.days
        )
        print("\n" + render_report(report))


def cmd_profile(args):
    from .sleep_profile import profile_for_range

    profile = profile_for_range(_client(args), args.date or dt.date.today(), days=args.days)
    if not profile:
        print("Not enough sleep data for a profile (need 10+ nights).")
        return
    print(f"\nSleep profile ({profile.nights} nights): "
          f"{profile.emoji} {profile.animal.upper()}")
    print(f"  {profile.description}")
    print(f"  avg sleep {profile.avg_duration_min // 60}h{profile.avg_duration_min % 60:02d} · "
          f"midpoint {profile.avg_midpoint} (±{profile.midpoint_std_min}min) · "
          f"deep {profile.deep_pct}% · REM {profile.rem_pct}% · "
          f"efficiency {profile.avg_efficiency}%")


def cmd_coach(args):
    from .coach import CoachError, CoachSession

    session = CoachSession(_client(args), date=args.date or dt.date.today())
    question = " ".join(args.question) if args.question else None

    def ask(text):
        reply = session.ask(text)
        prefix = "coach (with specialist) ⚡" if reply.used_specialist else "coach"
        print(f"\n{prefix}: {reply.text}\n")

    try:
        if question:
            ask(question)
            return
        print("Sense 2 coach — ask away (Ctrl-D or 'exit' to quit).")
        while True:
            try:
                text = input("you: ").strip()
            except EOFError:
                break
            if not text or text.lower() in {"exit", "quit"}:
                break
            ask(text)
    except CoachError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)


def cmd_webhook(args):
    from .automations import collect_events, deliver

    client = _client(args)
    events = collect_events(client, args.date or dt.date.today())
    state = Path(args.state) if args.state else None
    delivered = deliver(events, args.url, state_path=state)
    print(f"{len(delivered)} new event(s) delivered to {args.url} "
          f"({len(events) - len(delivered)} already sent).")
    for e in delivered:
        print(f"  → {e.event}: {e.payload}")


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
    add(
        "session",
        cmd_session,
        **{
            "--from": {"dest": "start", "required": True, "metavar": "HH:MM"},
            "--to": {"dest": "end", "required": True, "metavar": "HH:MM"},
            "--label": {"default": "Session"},
        },
    )
    add("training", cmd_training, **{"--days": {"type": int, "default": 42}})
    add("rhythm", cmd_rhythm, **{"--days": {"type": int, "default": 28}})
    add(
        "report",
        cmd_report,
        **{
            "--days": {"type": int, "default": 30},
            "--out": {"default": "sense2_wrapped.html"},
        },
    )
    add(
        "journal",
        cmd_journal,
        **{
            "action": {"choices": ["add", "remove", "list", "analyze"]},
            "tag": {"nargs": "?", "default": ""},
            "--days": {"type": int, "default": 90},
            "--journal": {"default": None, "help": "journal file path"},
        },
    )
    add(
        "webhook",
        cmd_webhook,
        **{
            "--url": {"required": True},
            "--state": {"default": None, "help": "state file path"},
        },
    )
    add("profile", cmd_profile, **{"--days": {"type": int, "default": 28}})
    add(
        "coach",
        cmd_coach,
        **{"question": {"nargs": "*", "help": "one-shot question (omit for chat mode)"}},
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
