"""\"Wrapped\"-style shareable report: stats, records, streaks and a
GitHub-style calendar heatmap of daily steps, rendered to a standalone HTML
file (inline SVG/CSS, no dependencies — the kind of artifact people post on
r/dataisbeautiful).

    python -m sense2 report --demo --days 60 --out wrapped.html
"""

from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

from .sleep_rhythm import rhythm_for_range
from .temp_rhythm import detect_shifts
from .training import training_for_range

HEAT_COLORS = ["#1a2232", "#0e4429", "#006d32", "#26a641", "#39d353"]


def gather(client, end: dt.date, days: int) -> dict:
    start = end - dt.timedelta(days=days - 1)
    steps = client.steps_series(start, end)
    azm = client.azm_series(start, end)
    sleep = client.sleep_series(start, end)
    rhr = client.resting_hr_series(start, end)
    hrv = client.hrv_series(start, end)

    step_values = [d["steps"] for d in steps]
    best_steps = max(steps, key=lambda d: d["steps"]) if steps else None
    best_rhr = min(rhr, key=lambda d: d["resting_hr"]) if rhr else None
    best_hrv = max(hrv, key=lambda d: d["rmssd"]) if hrv else None

    streak = longest = 0
    for d in steps:
        streak = streak + 1 if d["steps"] >= 8000 else 0
        longest = max(longest, streak)

    return {
        "profile": client.profile(),
        "start": str(start),
        "end": str(end),
        "days": days,
        "steps": steps,
        "total_steps": sum(step_values),
        "avg_steps": round(sum(step_values) / len(step_values)) if step_values else 0,
        "total_azm": sum(d["azm"] for d in azm),
        "avg_sleep_min": (
            round(sum(d["minutes_asleep"] for d in sleep) / len(sleep)) if sleep else 0
        ),
        "best_steps": best_steps,
        "best_rhr": best_rhr,
        "best_hrv": best_hrv,
        "streak_8k": longest,
        "training": training_for_range(client, end, days=min(days, 42)),
        "rhythm": rhythm_for_range(client, end, days=min(days, 28)),
        "temp": detect_shifts(client.skin_temp_series(start, end)),
    }


def _heatmap_svg(steps: list[dict]) -> str:
    """GitHub-style heatmap: columns are weeks, rows Mon..Sun."""
    if not steps:
        return ""
    values = sorted(d["steps"] for d in steps)

    def color(steps_count: int) -> str:
        if steps_count <= 0:
            return HEAT_COLORS[0]
        rank = sum(1 for v in values if v <= steps_count) / len(values)
        return HEAT_COLORS[min(4, 1 + int(rank * 4))]

    cell, gap = 13, 3
    first = dt.date.fromisoformat(steps[0]["date"])
    cells, month_labels, seen_months = [], [], set()
    for d in steps:
        date = dt.date.fromisoformat(d["date"])
        week = (date - first + dt.timedelta(days=first.weekday())).days // 7
        x, y = week * (cell + gap), date.weekday() * (cell + gap)
        cells.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" '
            f'fill="{color(d["steps"])}"><title>{d["date"]}: {d["steps"]:,} steps</title></rect>'
        )
        month_key = (date.year, date.month)
        if date.day <= 7 and month_key not in seen_months:
            seen_months.add(month_key)
            month_labels.append(
                f'<text x="{x}" y="{7 * (cell + gap) + 14}" fill="#8b96ab" '
                f'font-size="11">{date.strftime("%b")}</text>'
            )
    weeks = (dt.date.fromisoformat(steps[-1]["date"]) - first).days // 7 + 2
    width = weeks * (cell + gap)
    height = 7 * (cell + gap) + 20
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'style="max-width:{width}px">{"".join(cells)}{"".join(month_labels)}</svg>'
    )


def render_html(data: dict) -> str:
    name = html.escape(data["profile"].get("name") or "")
    training = data["training"]
    rhythm = data["rhythm"]
    best = data["best_steps"]
    records = [
        f"🏆 Biggest day: <b>{best['steps']:,} steps</b> on {best['date']}" if best else "",
        f"🔥 Longest 8k+ streak: <b>{data['streak_8k']} days</b>",
        (
            f"💙 Lowest resting HR: <b>{data['best_rhr']['resting_hr']} bpm</b> "
            f"on {data['best_rhr']['date']}"
        ) if data["best_rhr"] else "",
        (
            f"🧘 Best HRV: <b>{data['best_hrv']['rmssd']} ms</b> on {data['best_hrv']['date']}"
        ) if data["best_hrv"] else "",
    ]
    tiles = [
        (f"{data['total_steps']:,}", "total steps"),
        (f"{data['avg_steps']:,}", "steps / day"),
        (f"{data['total_azm']:,}", "active zone minutes"),
        (f"{data['avg_sleep_min'] // 60}h {data['avg_sleep_min'] % 60}m", "avg sleep"),
        (f"{training.fitness}", "fitness (CTL)"),
        (f"{training.form:+}", f"form — {training.label}"),
    ]
    tiles_html = "".join(
        f'<div class="tile"><b>{v}</b><span>{label}</span></div>' for v, label in tiles
    )
    records_html = "".join(f"<li>{r}</li>" for r in records if r)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Sense 2 Wrapped</title><style>
body {{ background:#0f1420; color:#e8ecf4; font-family:-apple-system,'Segoe UI',Roboto,sans-serif;
       max-width:880px; margin:0 auto; padding:32px 20px; }}
h1 {{ font-size:26px; margin-bottom:4px; }} h2 {{ font-size:15px; color:#8b96ab;
     text-transform:uppercase; letter-spacing:.06em; margin:28px 0 10px; }}
.muted {{ color:#8b96ab; font-size:13px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; }}
.tile {{ background:#1a2232; border-radius:12px; padding:14px; text-align:center; }}
.tile b {{ display:block; font-size:22px; }} .tile span {{ font-size:12px; color:#8b96ab; }}
ul {{ line-height:1.9; }} .card {{ background:#1a2232; border-radius:12px; padding:16px; }}
</style></head><body>
<h1>⌚ Sense 2 Wrapped{' — ' + name if name else ''}</h1>
<p class="muted">{data['start']} → {data['end']} · {data['days']} days · generated by Sense 2 Companion</p>
<h2>The numbers</h2><div class="tiles">{tiles_html}</div>
<h2>Daily steps</h2><div class="card">{_heatmap_svg(data['steps'])}</div>
<h2>Records</h2><ul>{records_html}</ul>
<h2>Training load</h2><p>Fitness {training.fitness} · fatigue {training.fatigue} ·
form {training.form:+} ({training.label}). {html.escape(training.advice)}
Last 7 days: {training.weekly_trimp} TRIMP.</p>
<h2>Sleep rhythm</h2><p>{html.escape(rhythm.summary)} Average sleep midpoint {rhythm.avg_midpoint}.</p>
<h2>Temperature</h2><p>{html.escape(data['temp'].summary)}</p>
<p class="muted">Estimates from Fitbit Web API data — not medical advice.</p>
</body></html>"""


def generate(client, end: dt.date, days: int, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.write_text(render_html(gather(client, end, days)))
    return out_path
