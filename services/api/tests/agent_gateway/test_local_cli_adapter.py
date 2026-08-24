import os
from pathlib import Path

import pytest

from vibe_visualization_api.agent_gateway.adapters.local_cli import (
    LocalCliAgentAdapter,
    ModWorkspaceUnavailableError,
    OpenChatCutMcpUnavailableError,
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
async def test_local_cli_returns_validated_artifacts(
    tmp_path: Path,
) -> None:
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "gateway.db",
        workspace_root=tmp_path,
        investment_workspace=tmp_path,
        trading_workspace=tmp_path,
        _env_file=None,
    )
    adapter = LocalCliAgentAdapter(
        "codex",
        settings,
        AgentConversationStore(settings.database_path),
    )
    adapter._executable = lambda: "/usr/bin/true"  # type: ignore[method-assign]

    async def artifact_answer(*_args: object) -> str:
        return (
            "结论正文。\n"
            '<vibedesk_artifacts>[{"kind":"report","title":"完整研究",'
            '"content":"报告正文"}]</vibedesk_artifacts>'
        )

    adapter._execute = artifact_answer  # type: ignore[method-assign]
    events = await _collect(
        adapter,
        AgentTaskCreate(module_id="market-daily", prompt="生成研究"),
    )

    assert events[-1].data["answer"] == "结论正文。"
    assert events[-1].data["artifacts"][0]["title"] == "完整研究"
    assert "vibedesk_artifacts" not in events[-1].data["answer"]


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


@pytest.mark.asyncio
async def test_workspace_resolver_uses_store_metadata_and_keeps_override_priority(
    tmp_path: Path,
) -> None:
    desk = tmp_path / "desk"
    investment = tmp_path / "investment"
    deepsee = tmp_path / "deepsee"
    cycle = tmp_path / "cycle"
    instock = tmp_path / "instock"
    orchestra_frontend = tmp_path / "orchestra" / "frontend"
    override = tmp_path / "override"
    for path in (
        desk,
        investment,
        deepsee,
        cycle,
        instock,
        orchestra_frontend,
        override,
    ):
        path.mkdir(parents=True)
    resolved = {
        "industry-map": investment,
        "watchlist": investment,
        "deepsee-news": deepsee,
        "seven-cycle-research": cycle,
        "instock-czsc": instock,
        "orchestra-history": orchestra_frontend,
        "market-daily": desk,
    }
    calls: list[str] = []

    async def resolve_workspace(module_id: str) -> Path | None:
        calls.append(module_id)
        return resolved.get(module_id)

    settings = Settings(
        workspace_root=desk,
        investment_workspace=investment,
        trading_workspace=desk,
        mod_workspace_overrides=f'{{"industry-map": "{override}"}}',
        _env_file=None,
    )
    adapter = LocalCliAgentAdapter(
        "codex",
        settings,
        AgentConversationStore(tmp_path / "gateway.db"),
        workspace_resolver=resolve_workspace,
    )

    assert await adapter._workspace_for("industry-map") == override.resolve()
    assert "industry-map" not in calls
    assert await adapter._workspace_for("watchlist") == investment.resolve()
    assert await adapter._workspace_for("deepsee-news") == deepsee.resolve()
    assert await adapter._workspace_for("seven-cycle-research") == cycle.resolve()
    assert await adapter._workspace_for("instock-czsc") == instock.resolve()
    assert await adapter._workspace_for("orchestra-history") == orchestra_frontend.resolve()
    assert await adapter._workspace_for("market-daily") == desk.resolve()


@pytest.mark.asyncio
async def test_workspace_resolver_does_not_fall_back_to_entire_desk(
    tmp_path: Path,
) -> None:
    async def unresolved(_module_id: str) -> Path | None:
        return None

    settings = Settings(
        workspace_root=tmp_path,
        _env_file=None,
    )
    adapter = LocalCliAgentAdapter(
        "codex",
        settings,
        AgentConversationStore(tmp_path / "gateway.db"),
        workspace_resolver=unresolved,
    )

    with pytest.raises(ModWorkspaceUnavailableError):
        await adapter._workspace_for("unregistered-mod")

    adapter._executable = lambda: "/usr/bin/true"  # type: ignore[method-assign]
    events = await _collect(
        adapter,
        AgentTaskCreate(module_id="unregistered-mod", prompt="修改页面"),
    )
    assert events[-1].type == "failed"
    assert events[-1].data["code"] == "workspace_unavailable"


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


def test_qoder_and_minimax_use_their_installed_binary_names_and_batch_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("qodercli", "mmx"):
        executable = tmp_path / name
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("NEWMA_DESK_AGENT_MINIMAX_BASE_URL", "https://api.minimaxi.com")
    settings = Settings(workspace_root=tmp_path, _env_file=None)
    store = AgentConversationStore(tmp_path / "gateway.db")
    qoder = LocalCliAgentAdapter("qoder", settings, store)
    minimax = LocalCliAgentAdapter("minimax", settings, store)

    assert qoder._executable() == str(tmp_path / "qodercli")
    assert minimax._executable() == str(tmp_path / "mmx")
    qoder_command = qoder._command(
        str(tmp_path / "qodercli"),
        tmp_path,
        "prompt",
        tmp_path / "answer",
        False,
        "batch",
        "cheap-model",
    )
    minimax_command = minimax._command(
        str(tmp_path / "mmx"),
        tmp_path,
        "prompt",
        tmp_path / "answer",
        False,
        "batch",
        "MiniMax-M3",
    )

    assert qoder_command[:2] == [str(tmp_path / "qodercli"), "--print"]
    assert "--no-session-persistence" in qoder_command
    assert qoder_command[-3:] == ["--model", "cheap-model", "prompt"]
    assert minimax_command[:3] == [
        str(tmp_path / "mmx"),
        "--base-url",
        "https://api.minimaxi.com",
    ]
    assert minimax_command[-2:] == ["--model", "MiniMax-M3"]


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
    assert "关键结论应引用 evidence id、source 与 asOf" in prompt
    assert "不得用模型常识静默补齐缺失数据" in prompt


def test_integrated_build_policy_is_selected_by_resolved_workspace(
    tmp_path: Path,
) -> None:
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
        module_id="future-imported-mod",
        capability="module.edit",
        prompt="修改当前量化页面",
        context={"vibedesk": {"mode": "edit"}},
    )

    prompt = adapter._build_prompt(request, [], trading, allow_write=True)

    assert "Vibe Trading 已内置到 Newma-Desk" in prompt
    assert "VITE_BASE_PATH=/mod-runtime/trading/" in prompt


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


def _openchatcut_request() -> AgentTaskCreate:
    return AgentTaskCreate(
        module_id="creator-transwrite",
        capability="module.edit",
        prompt="按当前分镜完成粗剪",
        context={
            "vibedesk": {
                "mode": "edit",
                "page": {
                    "selection": {
                        "runId": "run-1",
                        "stageId": "transwrite",
                        "nodeId": "roughcut",
                    },
                    "data": {
                        "summary": {
                            "selectedNode": {
                                "parameters": {},
                                "editorSession": {
                                    "sessionId": "editor-1",
                                    "selectedEditorId": "openchatcut",
                                    "externalProject": {
                                        "projectId": "occ-project-1"
                                    },
                                    "collaboration": {"status": "drafting"},
                                },
                            }
                        }
                    },
                },
            }
        },
    )


def test_openchatcut_collaboration_injects_mcp_without_leaking_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEWMA_DESK_OPENCHATCUT_MCP_TOKEN", "top-secret-token")
    monkeypatch.setenv(
        "NEWMA_DESK_OPENCHATCUT_MCP_ORIGIN", "http://127.0.0.1:5199"
    )
    settings = Settings(workspace_root=tmp_path, _env_file=None)
    adapter = LocalCliAgentAdapter(
        "codex",
        settings,
        AgentConversationStore(tmp_path / "gateway.db"),
    )
    request = _openchatcut_request()

    runtime = adapter._openchatcut_mcp_runtime(request)
    assert runtime is not None
    command = adapter._command(
        "codex",
        tmp_path,
        "prompt",
        tmp_path / "answer",
        True,
        openchatcut_mcp=runtime,
    )
    prompt = adapter._build_prompt(
        request,
        [],
        tmp_path,
        allow_write=True,
        openchatcut_mcp=runtime,
    )

    assert "read-only" in command
    assert any("mcp_servers.openchatcut.url" in item for item in command)
    assert any("bearer_token_env_var" in item for item in command)
    assert any(
        'default_tools_approval_mode="approve"' in item for item in command
    )
    assert "top-secret-token" not in " ".join(command)
    assert "begin_edit_session(approvalMode=manual)" in prompt
    assert "target_project(projectId=occ-project-1)" in prompt
    assert "creator.editor.review-proposal" in prompt
    assert "decision 只能使用 applied / rejected / discarded" in prompt
    assert "creator.editor.import-export" in prompt
    assert "top-secret-token" not in prompt


def test_openchatcut_collaboration_requires_a_ready_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEWMA_DESK_OPENCHATCUT_MCP_TOKEN", raising=False)
    monkeypatch.delenv("OPENCHATCUT_MCP_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = Settings(workspace_root=tmp_path, _env_file=None)
    adapter = LocalCliAgentAdapter(
        "codex",
        settings,
        AgentConversationStore(tmp_path / "gateway.db"),
    )

    with pytest.raises(OpenChatCutMcpUnavailableError):
        adapter._openchatcut_mcp_runtime(_openchatcut_request())


def test_cli_binary_override_prefers_current_codex_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "codex-current"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("NEWMA_DESK_AGENT_CODEX_BIN", str(executable))
    adapter = LocalCliAgentAdapter(
        "codex",
        Settings(workspace_root=tmp_path, _env_file=None),
        AgentConversationStore(tmp_path / "gateway.db"),
    )

    assert adapter._executable() == str(executable)
