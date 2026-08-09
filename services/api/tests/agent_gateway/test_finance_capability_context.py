import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.ai_context.finance_capabilities import (
    FinanceCapabilityContextEnricher,
)
from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.main import create_app

from .fakes import FakeAgentAdapter


REGISTRY = {
    "projects": [
        {
            "id": "day1global-skills",
            "name": "Day1Global Skills",
            "mode": "agent-capability",
            "presentation": "agent-only",
            "consumers": ["global-intelligence", "equity-research"],
            "capabilities": ["macro-liquidity-report", "tech-earnings-report"],
            "access": {"optionalSecrets": ["MUST_NOT_LEAK"]},
            "source": "https://example.invalid/private-runtime-detail",
        },
        {
            "id": "anthropic-financial-services",
            "name": "Anthropic Financial Services",
            "mode": "agent-capability",
            "presentation": "agent-only",
            "consumers": ["equity-research"],
            "capabilities": ["dcf-model", "comps-analysis"],
            "access": {"optionalSecrets": ["ANTHROPIC_API_KEY"]},
        },
        {
            "id": "reference-pack",
            "name": "Reference Pack",
            "mode": "reference-only",
            "consumers": ["global-intelligence"],
            "capabilities": ["unapproved-report"],
        },
    ]
}


def _write_registry(tmp_path: Path) -> Path:
    path = tmp_path / "finance-project-intake.json"
    path.write_text(json.dumps(REGISTRY), encoding="utf-8")
    return path


def _publish_module(
    repository: ModuleRepository,
    module_id: str,
    project_id: str,
) -> None:
    draft = repository.create_draft(
        {
            "id": module_id,
            "navigation": {"project": {"id": project_id}},
        }
    )
    repository.publish(module_id, draft.revision)


@pytest.mark.asyncio
async def test_current_column_receives_only_matching_agent_capabilities(
    tmp_path: Path,
) -> None:
    repository = ModuleRepository(tmp_path / "mods.db")
    _publish_module(repository, "global-monitor", "global-intelligence")
    enricher = FinanceCapabilityContextEnricher(
        _write_registry(tmp_path),
        lambda: repository,
    )

    request = await enricher.enrich(
        AgentTaskCreate(
            module_id="global-monitor",
            capability="module.explain",
            prompt="总结海外环境",
            context={
                "vibedesk": {
                    "mode": "ask",
                    "agentOnlyCapabilities": {
                        "sources": [{"id": "browser-spoof"}]
                    },
                }
            },
        )
    )

    capability_context = request.context["vibedesk"]["agentOnlyCapabilities"]
    assert capability_context["projectId"] == "global-intelligence"
    assert capability_context["sources"] == [
        {
            "id": "day1global-skills",
            "name": "Day1Global Skills",
            "capabilities": [
                "macro-liquidity-report",
                "tech-earnings-report",
            ],
        }
    ]
    serialized = json.dumps(capability_context)
    assert "browser-spoof" not in serialized
    assert "optionalSecrets" not in serialized
    assert "MUST_NOT_LEAK" not in serialized
    assert "private-runtime-detail" not in serialized


@pytest.mark.asyncio
async def test_day1global_is_agent_only_for_equity_and_not_added_to_edit_mode(
    tmp_path: Path,
) -> None:
    repository = ModuleRepository(tmp_path / "mods.db")
    _publish_module(repository, "stock-research", "equity-research")
    enricher = FinanceCapabilityContextEnricher(
        _write_registry(tmp_path),
        lambda: repository,
    )

    ask = await enricher.enrich(
        AgentTaskCreate(
            module_id="stock-research",
            capability="module.explain",
            prompt="分析公司",
            context={"vibedesk": {"mode": "ask"}},
        )
    )
    edit = await enricher.enrich(
        AgentTaskCreate(
            module_id="stock-research",
            capability="module.edit",
            prompt="修改页面",
            context={
                "vibedesk": {
                    "mode": "edit",
                    "agentOnlyCapabilities": {"sources": [{"id": "spoof"}]},
                }
            },
        )
    )

    source_ids = {
        source["id"]
        for source in ask.context["vibedesk"]["agentOnlyCapabilities"]["sources"]
    }
    assert source_ids == {
        "day1global-skills",
        "anthropic-financial-services",
    }
    assert "agentOnlyCapabilities" not in edit.context["vibedesk"]


def test_create_app_injects_capabilities_after_the_browser_request(
    tmp_path: Path,
) -> None:
    adapter = FakeAgentAdapter()
    application = create_app(
        Settings(
            runtime_dir=tmp_path,
            database_path=tmp_path / "gateway.db",
            agent_default_adapter=adapter.id,
            finance_project_intake_descriptor=_write_registry(tmp_path),
        ),
        agent_adapters=[adapter],
    )
    repository = application.state.resolve_module_repository()
    _publish_module(repository, "global-monitor", "global-intelligence")

    with TestClient(application) as client:
        response = client.post(
            "/api/agent/tasks",
            json={
                "moduleId": "global-monitor",
                "capability": "module.explain",
                "prompt": "分析海外市场",
                "context": {"vibedesk": {"mode": "ask"}},
            },
        )
        assert response.status_code == 202
        # The public task record keeps the browser payload; enrichment is
        # server-side and reaches only the selected Agent adapter.
        assert "agentOnlyCapabilities" not in response.json()["request"]["context"][
            "vibedesk"
        ]
        deadline = time.monotonic() + 2
        while not adapter.requests and time.monotonic() < deadline:
            time.sleep(0.01)

    assert adapter.requests
    routed = adapter.requests[0].context["vibedesk"]["agentOnlyCapabilities"]
    assert [source["id"] for source in routed["sources"]] == [
        "day1global-skills"
    ]
