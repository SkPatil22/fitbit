"""AI health coach — recreation of Fitbit Premium's Gemini-powered coach.

Architecture: a fast model (Claude Haiku 4.5) handles the conversation,
grounded in a compact summary of your Sense 2 data. It carries one tool,
`consult_specialist`, which escalates to a more capable model (Claude Sonnet
4.6 with adaptive thinking) for the heavy work — multi-week workout plans,
deep multi-metric analysis — and weaves the result back into its reply.

Requires ANTHROPIC_API_KEY (https://platform.claude.com). The Anthropic
client is injectable so tests run without credentials or network.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field

FAST_MODEL = "claude-haiku-4-5"
DEEP_MODEL = "claude-sonnet-4-6"
FAST_MAX_TOKENS = 2048
DEEP_MAX_TOKENS = 8000
MAX_TOOL_ROUNDS = 4

COACH_SYSTEM = """\
You are the Sense 2 Companion coach: a friendly, evidence-minded health and
fitness coach working from the wearer's real Fitbit Sense 2 data (provided
below). Ground every answer in that data — cite the actual numbers — and say
so plainly when the data can't answer something. Keep replies short and
conversational (a few sentences, bullets when listing). You are not a doctor;
for medical concerns, say so and suggest professional care.

For heavyweight requests — building a workout or training plan, a deep dive
across several weeks of metrics, anything needing thorough multi-step
reasoning — call the consult_specialist tool with a complete, self-contained
task description, then present its findings conversationally. Handle quick
questions yourself without the tool."""

SPECIALIST_SYSTEM = """\
You are an exercise physiology and sleep science specialist producing
thorough, structured analysis for a health coach to relay. You are given the
wearer's real Fitbit Sense 2 data summary and a task. Reason carefully over
the actual numbers, state assumptions, and produce a complete, actionable
deliverable (e.g. a week-by-week plan with sets/intensities anchored to their
training load and recovery, or a structured analysis with concrete findings).
Use markdown. Not medical advice; flag anything that warrants a clinician."""

SPECIALIST_TOOL = {
    "name": "consult_specialist",
    "description": (
        "Delegate a heavyweight task to the specialist model (more capable, "
        "slower, more expensive). Call this when the user asks for a workout "
        "or training plan, a multi-week deep analysis of their metrics, or "
        "anything else needing long structured reasoning — not for quick "
        "factual questions about today's data. Provide a complete task "
        "description including the user's goals and constraints; the "
        "specialist sees the same health data summary but not the chat."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Complete, self-contained task for the specialist.",
            },
        },
        "required": ["task"],
    },
}


class CoachError(Exception):
    pass


@dataclass
class CoachReply:
    text: str
    used_specialist: bool = False
    specialist_tasks: list = field(default_factory=list)


def build_health_context(client, date: dt.date, trend_days: int = 14) -> str:
    """Compact data summary both models are grounded in."""
    from .health_alerts import health_check
    from .readiness import readiness_for_date
    from .sleep_profile import profile_for_range
    from .sleep_rhythm import rhythm_for_range
    from .stress import stress_for_date
    from .training import training_for_range

    profile = client.profile()
    readiness = readiness_for_date(client, date)
    stress = stress_for_date(client, date)
    health = health_check(client, date)
    training = training_for_range(client, date, days=trend_days)
    rhythm = rhythm_for_range(client, date)
    sleep_animal = profile_for_range(client, date)
    sleep = client.sleep_summary(date)
    hrv = client.hrv_daily(date)
    spo2 = client.spo2(date)
    br = client.breathing_rate(date)
    temp = client.skin_temp(date)
    resting_hr = client.heart_intraday(date)["resting_hr"]

    start = date - dt.timedelta(days=trend_days - 1)
    rhr_series = [d["resting_hr"] for d in client.resting_hr_series(start, date)]
    steps_series = [d["steps"] for d in client.steps_series(start, date)]

    lines = [
        f"WEARER: {profile.get('name') or 'user'}, age {profile.get('age') or 'unknown'}. "
        f"Data date: {date} ({date.strftime('%A')}).",
        "",
        f"READINESS: {readiness.score}/100 [{readiness.label}] "
        f"(HRV {readiness.hrv_score}, resting-HR {readiness.rhr_score}, sleep {readiness.sleep_score}). "
        f"{readiness.recommendation}",
        f"STRESS TODAY: avg {stress.daily_avg}/100, peak {stress.peak}"
        + (
            "; episodes: " + ", ".join(f"{e.start}-{e.end} (peak {e.peak})" for e in stress.episodes)
            if stress.episodes else "; no sustained episodes"
        ),
        f"HEALTH CHECK: {health.level.upper()} — {health.summary}"
        + ("".join(f"\n  - {s.message}" for s in health.signals) if health.signals else ""),
        "",
        "VITALS (last night): "
        + ", ".join(
            part for part in (
                f"resting HR {resting_hr} bpm" if resting_hr else "",
                f"HRV {hrv['rmssd']} ms" if hrv else "",
                f"breathing {br['rate']}/min" if br else "",
                f"SpO2 {spo2['avg']}%" if spo2 else "",
                f"skin temp {temp['nightly_relative']:+.1f}°C vs baseline" if temp else "",
            ) if part
        ),
        (
            f"SLEEP (last night): {sleep['minutes_asleep'] // 60}h{sleep['minutes_asleep'] % 60:02d}, "
            f"{sleep['efficiency']}% efficiency, stages {sleep['stages']}"
            if sleep else "SLEEP: no data for last night"
        ),
        "",
        f"TRAINING LOAD ({trend_days}d): fitness {training.fitness}, fatigue {training.fatigue}, "
        f"form {training.form:+} [{training.label}]; last-7d TRIMP {training.weekly_trimp}. "
        f"{training.advice}",
        f"SLEEP RHYTHM (28d): {rhythm.summary}",
        (
            f"SLEEP PROFILE (28d): {sleep_animal.animal} {sleep_animal.emoji} — "
            f"avg {sleep_animal.avg_duration_min // 60}h{sleep_animal.avg_duration_min % 60:02d}, "
            f"midpoint {sleep_animal.avg_midpoint} ±{sleep_animal.midpoint_std_min}min, "
            f"deep {sleep_animal.deep_pct}%, REM {sleep_animal.rem_pct}%"
            if sleep_animal else "SLEEP PROFILE: not enough nights yet"
        ),
        "",
        f"TRENDS ({trend_days}d): resting HR {min(rhr_series)}-{max(rhr_series)} bpm "
        f"(avg {sum(rhr_series) / len(rhr_series):.0f}); "
        f"steps avg {sum(steps_series) / len(steps_series):,.0f}/day"
        if rhr_series and steps_series else "",
    ]
    return "\n".join(line for line in lines if line is not None)


class CoachSession:
    """Multi-turn chat with the fast model, escalating via tool use."""

    def __init__(self, fitbit_client, date: dt.date | None = None,
                 anthropic_client=None):
        self.fitbit = fitbit_client
        self.date = date or dt.date.today()
        self.messages: list = []
        self._context: str | None = None
        self._anthropic = anthropic_client

    def _client(self):
        if self._anthropic is None:
            if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
                raise CoachError(
                    "The coach needs an Anthropic API key. Set ANTHROPIC_API_KEY "
                    "(get one at https://platform.claude.com) and try again."
                )
            import anthropic

            self._anthropic = anthropic.Anthropic()
        return self._anthropic

    def _health_context(self) -> str:
        if self._context is None:
            self._context = build_health_context(self.fitbit, self.date)
        return self._context

    def _system(self, prompt: str) -> list:
        # Stable prompt + data context first, cacheable across the conversation.
        return [
            {
                "type": "text",
                "text": f"{prompt}\n\n=== WEARER'S SENSE 2 DATA ===\n{self._health_context()}",
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _consult_specialist(self, task: str) -> str:
        response = self._client().messages.create(
            model=DEEP_MODEL,
            max_tokens=DEEP_MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=self._system(SPECIALIST_SYSTEM),
            messages=[{"role": "user", "content": task}],
        )
        return "".join(b.text for b in response.content if b.type == "text")

    def ask(self, user_message: str) -> CoachReply:
        client = self._client()
        self.messages.append({"role": "user", "content": user_message})
        used_specialist = False
        specialist_tasks: list[str] = []

        for _ in range(MAX_TOOL_ROUNDS):
            response = client.messages.create(
                model=FAST_MODEL,
                max_tokens=FAST_MAX_TOKENS,
                system=self._system(COACH_SYSTEM),
                tools=[SPECIALIST_TOOL],
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type == "tool_use" and block.name == "consult_specialist":
                    used_specialist = True
                    task = block.input.get("task", "")
                    specialist_tasks.append(task)
                    try:
                        result = self._consult_specialist(task)
                        tool_results.append(
                            {"type": "tool_result", "tool_use_id": block.id, "content": result}
                        )
                    except Exception as exc:
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Specialist unavailable: {exc}",
                                "is_error": True,
                            }
                        )
            self.messages.append({"role": "user", "content": tool_results})

        text = ""
        for msg in reversed(self.messages):
            if msg["role"] == "assistant":
                text = "".join(
                    b.text for b in msg["content"] if getattr(b, "type", None) == "text"
                )
                break
        return CoachReply(text=text, used_specialist=used_specialist,
                          specialist_tasks=specialist_tasks)
