import os
from pathlib import Path

import pytest

from vibe_visualization_api.agent_gateway.adapters.local_cli import (
    LocalCliAgentAdapter,
)
from vibe_visualization_api.agent_gateway.conversation_store import (
    AgentConversationStore,
)
from vibe_visualization_api.agent_gateway.preferences import AgentPreferenceStore
from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.config import Settings


def _fake_codex(path: Path) -> Path:
    executable = path / "codex"
    executable.write_text(
        """#!/usr/bin/env python3
import pathlib
import sys

prompt = sys.stdin.read()
out_index = sys.argv.index("--output-last-message") + 1
answer = "MEMORY_OK" if "FIRST_ANSWER" in prompt else "FIRST_ANSWER"
pathlib.Path(sys.argv[out_index]).write_text(answer, encoding="utf-8")
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


async def _collect(adapter: LocalCliAgentAdapter, request: AgentTaskCreate):
    return [event async for event in adapter.run("task-1", request)]


def test_agent_stores_initialize_only_when_first_used(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "gateway.db"
    conversation_store = AgentConversationStore(database_path)
    preference_store = AgentPreferenceStore(database_path)

    assert database_path.exists() is False

    preferences = preference_store.get("local-user", "codex")

    assert preferences.default_adapter == "codex"
    assert database_path.exists() is True
    assert conversation_store.recent(
        "local-user",
        "codex",
        "quant-agent",
    ) == []


@pytest.mark.asyncio
async def test_codex_cli_runs_and_reuses_module_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_codex(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "gateway.db",
        workspace_root=tmp_path,
        investment_workspace=tmp_path,
        trading_workspace=tmp_path,
        agent_timeout_seconds=5,
    )
    adapter = LocalCliAgentAdapter(
        "codex",
        settings,
        AgentConversationStore(settings.database_path),
    )

    first = await _collect(
        adapter,
        AgentTaskCreate(module_id="quant-agent", prompt="first"),
    )
    second = await _collect(
        adapter,
        AgentTaskCreate(module_id="quant-agent", prompt="second"),
    )

    assert [event.type for event in first] == ["progress", "completed"]
    assert first[-1].data["answer"] == "FIRST_ANSWER"
    assert second[-1].data["answer"] == "MEMORY_OK"
    description = await adapter.describe()
    assert description["available"] is True
    assert description["supportsMemory"] is True


@pytest.mark.asyncio
async def test_missing_cli_returns_safe_failed_event(tmp_path: Path) -> None:
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "gateway.db",
        workspace_root=tmp_path,
        investment_workspace=tmp_path,
        trading_workspace=tmp_path,
    )
    adapter = LocalCliAgentAdapter(
        "gemini",
        settings,
        AgentConversationStore(settings.database_path),
    )
    adapter._executable = lambda: None  # type: ignore[method-assign]

    events = await _collect(
        adapter,
        AgentTaskCreate(module_id="daily-review", prompt="hello"),
    )

    assert events[-1].type == "failed"
    assert events[-1].data["code"] == "cli_unavailable"
