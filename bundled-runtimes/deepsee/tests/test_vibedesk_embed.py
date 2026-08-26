from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = PROJECT_ROOT / "static" / "index.html"
BRIDGE_JS = PROJECT_ROOT / "static" / "modules" / "vibedesk-embed.js"
BRIDGE_CSS = PROJECT_ROOT / "static" / "modules" / "vibedesk-embed.css"


def test_each_deepsee_panel_has_an_addressable_embed_route() -> None:
    from app.main import VIBEDESK_EMBED_MODULES, create_app

    app = create_app()
    route = next(item for item in app.routes if item.path == "/embed/{module_id}")

    for module_id in sorted(VIBEDESK_EMBED_MODULES):
        response = asyncio.run(route.endpoint(module_id))
        assert response.status_code == 200
        assert response.headers["x-vibedesk-mod"] == module_id

    assert asyncio.run(route.endpoint("not-a-module")).status_code == 404


def test_unified_ui_loads_the_vibedesk_embed_adapter() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert '<link rel="stylesheet" href="/static/modules/vibedesk-embed.css?v=20260730-theme6">' in source
    assert '<script src="/static/modules/vibedesk-embed.js?v=20260819"></script>' in source
    assert BRIDGE_JS.is_file()
    assert BRIDGE_CSS.is_file()
    css = BRIDGE_CSS.read_text(encoding="utf-8")
    assert "flex-wrap: wrap" in css
    assert "overflow-x: hidden" in css


def test_settings_embed_preserves_deepsee_secondary_navigation() -> None:
    source = BRIDGE_JS.read_text(encoding="utf-8")
    css = BRIDGE_CSS.read_text(encoding="utf-8")

    assert "activateEmbeddedModule" in source
    assert "window.__BOOTSTRAPPED__" in source
    assert "tab.click()" in source
    assert "ensureSettingsSecondaryNavigation" in source
    assert "buildSettingsSecondaryNavigationFallback" in source
    assert "#function-settings .settings-layout" in css
    assert "min-height: calc(100vh - 16px)" in css
    assert "max-height: calc(100vh - 16px)" in css


def test_vibedesk_bridge_has_valid_javascript_syntax() -> None:
    result = subprocess.run(
        ["node", "--check", str(BRIDGE_JS)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_vibedesk_bridge_keeps_agent_and_model_gateways_separate() -> None:
    source = BRIDGE_JS.read_text(encoding="utf-8")

    assert "createAgentTask" in source
    assert "'/api/agent/tasks'" in source
    assert "createModelResponse" in source
    assert "'/api/model/responses'" in source
    assert "window.__autoModuleRefreshBound = true" in source


def test_vibedesk_bridge_supports_manifest_actions_and_context() -> None:
    source = BRIDGE_JS.read_text(encoding="utf-8")

    assert "vibedesk:hello" in source
    assert "vibedesk:init" in source
    assert "vibedesk:ack" in source
    assert "vibedesk:action-request" in source
    assert "vibedesk:action-result" in source
    assert "vibedesk:context-request" in source
    assert "waitForTask" in source


def test_deepsee_ai_and_news_use_desk_agent_actions_when_embedded() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert "deepsee.insights.analyze" in source
    assert "deepsee.news.batch-analyze" in source
    assert 'id="newsBatchAnalyzeBtn"' in source
    assert "runDeskAgentInsight" in source


def test_deepsee_agent_analysis_uses_bounded_page_evidence() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")
    insight_source = source.split("async function runDeskAgentInsight", 1)[1].split(
        "let lastAnalyzedMessages", 1
    )[0]
    news_source = source.split("async function runNewsBatchAnalysis", 1)[1].split(
        "function bindNewsEngineControls", 1
    )[0]

    assert ".slice(0, 80)" in insight_source
    assert ".slice(0, 600)" in insight_source
    assert "不扫描项目、数据库或其他文件" in insight_source
    assert "如果 evidence 为空" in insight_source
    assert "evidence," in insight_source
    assert ".slice(0, 80)" in news_source
    assert "items.slice(0, 30)" in news_source
    assert ".slice(0, 120)" in news_source


def test_vibedesk_embed_consumes_the_newma_theme_contract() -> None:
    source = BRIDGE_JS.read_text(encoding="utf-8")
    css = BRIDGE_CSS.read_text(encoding="utf-8")

    assert "applyAppearance" in source
    assert "appearance.cssVars" in source
    assert "document.documentElement.dataset.theme" in source
    assert "document.documentElement.style.colorScheme" in source
    assert "newma:themechange" in source
    assert "--bg: var(--vibe-bg, #f4efe3)" in css
    assert "--bg: var(--vibe-bg, #0f1714)" in css
    assert "--brand-accent: var(--vibe-accent" in css
