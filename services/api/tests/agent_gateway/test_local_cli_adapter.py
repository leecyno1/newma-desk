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
async def test_codex_cli_task_scope_does_not_read_or_persist_memory(
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
    request = AgentTaskCreate(
        module_id="quant-agent",
        prompt="single task",
        memory_scope="task",
    )

    first = await _collect(adapter, request)
    second = await _collect(adapter, request)

    assert first[-1].data["answer"] == "FIRST_ANSWER"
    assert second[-1].data["answer"] == "FIRST_ANSWER"
    assert second[-1].data["memory"] == "task"


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


def test_workspace_resolver_covers_external_mod_families(tmp_path: Path) -> None:
    desk = tmp_path / "desk"
    investment = tmp_path / "investment"
    deepsee = tmp_path / "deepsee"
    cycle = tmp_path / "cycle"
    instock = tmp_path / "instock"
    orchestra_root = tmp_path / "orchestra"
    orchestra_frontend = orchestra_root / "frontend"
    orchestra_backend = orchestra_root / "backend"
    override = tmp_path / "override"
    for path in (
        desk,
        investment,
        deepsee,
        cycle,
        instock,
        orchestra_frontend,
        orchestra_backend,
        override,
    ):
        path.mkdir(parents=True)
    settings = Settings(
        workspace_root=desk,
        investment_workspace=investment,
        trading_workspace=desk,
        deepsee_workspace=deepsee,
        seven_cycle_workspace=cycle,
        instock_workspace=instock,
        orchestra_frontend_workspace=orchestra_frontend,
        orchestra_backend_workspace=orchestra_backend,
        mod_workspace_overrides=f'{{"industry-map": "{override}"}}',
        _env_file=None,
    )
    adapter = LocalCliAgentAdapter(
        "codex",
        settings,
        AgentConversationStore(tmp_path / "gateway.db"),
    )

    assert adapter._workspace_for("industry-map") == override.resolve()
    assert adapter._workspace_for("watchlist") == investment.resolve()
    assert adapter._workspace_for("deepsee-news") == deepsee.resolve()
    assert adapter._workspace_for("seven-cycle-research") == cycle.resolve()
    assert adapter._workspace_for("instock-czsc") == instock.resolve()
    assert adapter._workspace_for("orchestra-history") == orchestra_root.resolve()
    assert adapter._workspace_for("market-daily") == desk.resolve()


def test_write_access_requires_explicit_edit_mode(tmp_path: Path) -> None:
    settings = Settings(workspace_root=tmp_path, _env_file=None)
    adapter = LocalCliAgentAdapter(
        "codex",
        settings,
        AgentConversationStore(tmp_path / "gateway.db"),
    )
    ask = AgentTaskCreate(
        module_id="market-daily",
        capability="module.explain",
        prompt="解释页面",
        context={"vibedesk": {"mode": "ask"}},
    )
    edit = AgentTaskCreate(
        module_id="market-daily",
        capability="module.edit",
        prompt="修改页面",
        context={"vibedesk": {"mode": "edit"}},
    )

    assert adapter._allows_write(ask) is False
    assert adapter._allows_write(edit) is True
    assert "read-only" in adapter._command(
        "codex", tmp_path, "prompt", tmp_path / "answer", False
    )
    assert "workspace-write" in adapter._command(
        "codex", tmp_path, "prompt", tmp_path / "answer", True
    )


def test_finance_mod_prompt_requires_global_stock_data_skill(tmp_path: Path) -> None:
    investment = tmp_path / "vibe-research"
    trading = tmp_path / "vibe-trading"
    investment.mkdir()
    trading.mkdir()
    settings = Settings(
        workspace_root=tmp_path,
        investment_workspace=investment,
        trading_workspace=trading,
        _env_file=None,
    )
    adapter = LocalCliAgentAdapter(
        "codex",
        settings,
        AgentConversationStore(tmp_path / "gateway.db"),
    )
    request = AgentTaskCreate(
        module_id="quant-agent",
        capability="quant.research",
        prompt="分析 AAPL 和腾讯控股",
    )

    prompt = adapter._build_prompt(request, [], trading)

    expected_skill = investment.resolve() / "global-stock-data" / "SKILL.md"
    assert str(expected_skill) in prompt
    assert "美股行情 Sina → Tencent → Eastmoney" in prompt
    assert "港股行情 Tencent → Sina → Eastmoney" in prompt
    assert "不得用 yfinance 作为美股/港股默认行情源" in prompt


def test_non_finance_mod_prompt_does_not_inject_market_data_policy(tmp_path: Path) -> None:
    settings = Settings(workspace_root=tmp_path, _env_file=None)
    adapter = LocalCliAgentAdapter(
        "codex",
        settings,
        AgentConversationStore(tmp_path / "gateway.db"),
    )
    request = AgentTaskCreate(module_id="market-daily", prompt="解释页面")

    prompt = adapter._build_prompt(request, [], tmp_path)

    assert "global-stock-data" not in prompt
