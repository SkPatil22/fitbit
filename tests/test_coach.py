import datetime as dt
from types import SimpleNamespace

import pytest

from sense2.coach import (
    DEEP_MODEL,
    FAST_MODEL,
    CoachError,
    CoachSession,
    build_health_context,
)
from sense2.demo_data import DemoClient

DATE = dt.date(2026, 6, 10)


def text_block(text):
    return SimpleNamespace(type="text", text=text)

def tool_block(task, block_id="tu_1"):
    return SimpleNamespace(
        type="tool_use", name="consult_specialist", input={"task": task}, id=block_id
    )

def response(content, stop_reason="end_turn"):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


class FakeAnthropic:
    """Plays back scripted responses and records every messages.create call."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # snapshot messages: the session mutates the same list after the call
        kwargs["messages"] = list(kwargs.get("messages", []))
        self.calls.append(kwargs)
        return self.script.pop(0)


def _session(script):
    fake = FakeAnthropic(script)
    return CoachSession(DemoClient(today=DATE), date=DATE, anthropic_client=fake), fake


def test_health_context_contains_all_sections():
    context = build_health_context(DemoClient(today=DATE), DATE)
    for section in ("READINESS", "STRESS TODAY", "HEALTH CHECK", "VITALS",
                    "TRAINING LOAD", "SLEEP RHYTHM", "SLEEP PROFILE", "TRENDS"):
        assert section in context


def test_quick_question_stays_on_fast_model():
    session, fake = _session([response([text_block("Readiness is 47 — take it easy.")])])
    reply = session.ask("How am I doing today?")

    assert reply.text == "Readiness is 47 — take it easy."
    assert reply.used_specialist is False
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == FAST_MODEL
    assert call["tools"][0]["name"] == "consult_specialist"
    assert "READINESS" in call["system"][0]["text"]
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_workout_plan_escalates_to_specialist():
    session, fake = _session([
        response([tool_block("Build a 4-week 10k plan")], stop_reason="tool_use"),
        response([text_block("## Week 1\nEasy runs...")]),       # specialist (Sonnet)
        response([text_block("Here's your plan: Week 1 ...")]),  # Haiku wrap-up
    ])
    reply = session.ask("Build me a 4-week 10k plan")

    assert reply.used_specialist is True
    assert reply.specialist_tasks == ["Build a 4-week 10k plan"]
    assert reply.text.startswith("Here's your plan")

    fast1, deep, fast2 = fake.calls
    assert fast1["model"] == FAST_MODEL
    assert deep["model"] == DEEP_MODEL
    assert deep["thinking"] == {"type": "adaptive"}
    assert "exercise physiology" in deep["system"][0]["text"]

    # the specialist's answer comes back to Haiku as a tool_result
    tool_results = fast2["messages"][-1]["content"]
    assert tool_results[0]["type"] == "tool_result"
    assert tool_results[0]["tool_use_id"] == "tu_1"
    assert "Week 1" in tool_results[0]["content"]


def test_specialist_failure_is_reported_as_tool_error():
    class ExplodingFake(FakeAnthropic):
        def _create(self, **kwargs):
            if kwargs["model"] == DEEP_MODEL:
                raise RuntimeError("boom")
            return super()._create(**kwargs)

    fake = ExplodingFake([
        response([tool_block("analyze everything")], stop_reason="tool_use"),
        response([text_block("Specialist is unavailable, but from my view...")]),
    ])
    session = CoachSession(DemoClient(today=DATE), date=DATE, anthropic_client=fake)
    reply = session.ask("Deep analysis please")

    assert reply.used_specialist is True
    error_result = fake.calls[-1]["messages"][-1]["content"][0]
    assert error_result["is_error"] is True
    assert "boom" in error_result["content"]


def test_multi_turn_history_accumulates():
    session, fake = _session([
        response([text_block("First answer")]),
        response([text_block("Second answer")]),
    ])
    session.ask("first?")
    session.ask("second?")
    sent = fake.calls[1]["messages"]
    assert sent[0] == {"role": "user", "content": "first?"}
    assert sent[2] == {"role": "user", "content": "second?"}


def test_missing_api_key_raises_coach_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    session = CoachSession(DemoClient(today=DATE), date=DATE)
    with pytest.raises(CoachError, match="ANTHROPIC_API_KEY"):
        session.ask("hello")
