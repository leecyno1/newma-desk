"""SessionService regressions for remote MCP startup paths."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.session.events import EventBus
from src.session.models import Attempt, Message, Session
from src.session.service import SessionService
from src.session.store import SessionStore


class _DummyIndex:
    def index_session(self, session_id: str, title: str) -> None:
        del session_id, title

    def index_message(self, session_id: str, role: str, content: str) -> None:
        del session_id, role, content


class _DummyAgentLoop:
    def __init__(self, *, registry, llm, event_callback, max_iterations, persistent_memory) -> None:
        del registry, llm, event_callback, max_iterations, persistent_memory

    def run(self, *, user_message: str, history, session_id: str) -> dict[str, str]:
        del user_message, history, session_id
        return {"status": "completed"}


class _SlowAgentLoop:
    def __init__(self, *, registry, llm, event_callback, max_iterations, persistent_memory) -> None:
        del registry, llm, event_callback, max_iterations, persistent_memory
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self, *, user_message: str, history, session_id: str) -> dict[str, str]:
        del user_message, history, session_id
        import time

        time.sleep(1.2)
        return {"status": "completed"}


def test_run_with_agent_keeps_event_loop_responsive_during_registry_build(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def _slow_build_registry(**kwargs):
        del kwargs
        time.sleep(0.25)
        return object()

    monkeypatch.setattr("src.session.service.get_shared_index", lambda: _DummyIndex())
    monkeypatch.setattr("src.tools.build_registry", _slow_build_registry)
    monkeypatch.setattr("src.providers.chat.ChatLLM", lambda: object())
    monkeypatch.setattr("src.memory.persistent.PersistentMemory", lambda: object())
    monkeypatch.setattr("src.agent.loop.AgentLoop", _DummyAgentLoop)
    monkeypatch.setattr("src.config.loader.load_runtime_agent_config", lambda overrides=None: object())
    monkeypatch.setattr("src.config.loader.sanitize_session_overrides", lambda overrides: dict(overrides))

    service = SessionService(
        store=SessionStore(tmp_path / "sessions"),
        event_bus=EventBus(),
        runs_dir=tmp_path / "runs",
    )
    attempt = Attempt(session_id="session-1", prompt="hello")

    async def _ticker(events: list[float], start: float) -> None:
        await asyncio.sleep(0.05)
        events.append(time.perf_counter() - start)

    async def _exercise() -> tuple[list[float], dict[str, str]]:
        events: list[float] = []
        start = time.perf_counter()
        asyncio.create_task(_ticker(events, start))
        result = await service._run_with_agent(attempt, messages=[], session_config={})
        await asyncio.sleep(0.01)
        return events, result

    tick_times, result = asyncio.run(_exercise())

    assert result["status"] == "completed"
    assert tick_times, "Expected the event loop ticker to run while registry build was pending"
    assert tick_times[0] < 0.18, f"Registry build blocked the event loop for too long: {tick_times[0]:.3f}s"


def test_run_with_agent_times_out_and_cancels_hung_loop(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VIBE_TRADING_AGENT_TIMEOUT_SECONDS", "1")
    monkeypatch.setattr("src.session.service.get_shared_index", lambda: _DummyIndex())
    monkeypatch.setattr("src.tools.build_registry", lambda **kwargs: object())
    monkeypatch.setattr("src.providers.chat.ChatLLM", lambda: object())
    monkeypatch.setattr("src.memory.persistent.PersistentMemory", lambda: object())
    monkeypatch.setattr("src.agent.loop.AgentLoop", _SlowAgentLoop)
    monkeypatch.setattr("src.config.loader.load_runtime_agent_config", lambda overrides=None: object())
    monkeypatch.setattr("src.config.loader.sanitize_session_overrides", lambda overrides: dict(overrides))

    service = SessionService(
        store=SessionStore(tmp_path / "sessions"),
        event_bus=EventBus(),
        runs_dir=tmp_path / "runs",
    )
    attempt = Attempt(session_id="session-1", prompt="hello")

    async def _exercise() -> None:
        with pytest.raises(TimeoutError, match="timed out"):
            await service._run_with_agent(attempt, messages=[], session_config={})

    asyncio.run(_exercise())


def test_get_messages_recovers_stale_successful_attempt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.session.service.get_shared_index", lambda: _DummyIndex())
    store = SessionStore(tmp_path / "sessions")
    session = store.create_session(Session(title="recover success"))
    attempt = Attempt(session_id=session.session_id, prompt="run a backtest")
    attempt.mark_running()
    attempt.created_at = (datetime.now() - timedelta(hours=1)).isoformat()
    store.create_attempt(attempt)
    session.last_attempt_id = attempt.attempt_id
    store.update_session(session)
    store.append_message(Message(session_id=session.session_id, role="user", content=attempt.prompt))

    run_dir = tmp_path / "runs" / "run-success"
    run_dir.mkdir(parents=True)
    (run_dir / "req.json").write_text(
        json.dumps({"prompt": attempt.prompt, "context": {"session_id": session.session_id}}),
        encoding="utf-8",
    )
    (run_dir / "state.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(
        json.dumps({"type": "answer", "content": "Recovered answer"}) + "\n",
        encoding="utf-8",
    )

    service = SessionService(store=store, event_bus=EventBus(), runs_dir=tmp_path / "runs")

    messages = service.get_messages(session.session_id)
    recovered = store.get_attempt(session.session_id, attempt.attempt_id)

    assert recovered is not None
    assert recovered.status.value == "completed"
    assert recovered.run_dir == str(run_dir)
    assert any(m.role == "assistant" and m.content == "Recovered answer" for m in messages)


def test_get_messages_marks_stale_running_attempt_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIBE_TRADING_AGENT_TIMEOUT_SECONDS", "60")
    monkeypatch.setattr("src.session.service.get_shared_index", lambda: _DummyIndex())
    store = SessionStore(tmp_path / "sessions")
    session = store.create_session(Session(title="recover stale"))
    attempt = Attempt(session_id=session.session_id, prompt="hung request")
    attempt.mark_running()
    attempt.created_at = (datetime.now() - timedelta(hours=1)).isoformat()
    store.create_attempt(attempt)
    session.last_attempt_id = attempt.attempt_id
    store.update_session(session)
    store.append_message(Message(session_id=session.session_id, role="user", content=attempt.prompt))

    service = SessionService(store=store, event_bus=EventBus(), runs_dir=tmp_path / "runs")

    messages = service.get_messages(session.session_id)
    recovered = store.get_attempt(session.session_id, attempt.attempt_id)

    assert recovered is not None
    assert recovered.status.value == "failed"
    assert "timed out" in (recovered.error or "")
    assert any(m.role == "assistant" and "timed out" in m.content for m in messages)
