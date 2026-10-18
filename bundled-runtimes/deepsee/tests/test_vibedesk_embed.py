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
    assert {"wechat-automation", "send-management"} <= VIBEDESK_EMBED_MODULES
    assert "'wechat-automation': 'deepsee-automation'" in BRIDGE_JS.read_text(encoding="utf-8")
    route = next(item for item in app.routes if item.path == "/embed/{module_id}")

    for module_id in sorted(VIBEDESK_EMBED_MODULES):
        response = asyncio.run(route.endpoint(module_id))
        assert response.status_code == 200
        assert response.headers["x-vibedesk-mod"] == module_id

    assert asyncio.run(route.endpoint("not-a-module")).status_code == 404


def test_unified_ui_loads_the_vibedesk_embed_adapter() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert '<link rel="stylesheet" href="/static/modules/vibedesk-embed.css?v=20261015-settings">' in source
    assert '<script src="/static/modules/vibedesk-embed.js?v=20261016-modules"></script>' in source
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
    assert "hideRuntimeOwnedSettings" in source
    assert "['settings-ai-config', 'settings-prompts']" in source
    assert "section.dataset.navHidden = '1'" in source
    assert 'html.vibedesk-embed .settings-section[data-nav-hidden="1"]' in css
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


def test_vibedesk_bridge_routes_agent_requests_through_the_runtime_seam() -> None:
    source = BRIDGE_JS.read_text(encoding="utf-8")

    assert "requestAgent" in source
    assert "vibedesk:copilot-open" in source
    assert "instanceId: state.instanceId" in source
    assert "modId: state.moduleId" in source
    assert "agentRuntimeAvailable" in source
    assert "value.owner === 'newma'" in source
    assert "value.owner === 'numa'" in source
    assert "value.owner === 'desk'" in source
    assert "/api/agent/tasks" not in source
    assert "/api/model/responses" not in source
    assert "window.__autoModuleRefreshBound = true" in source
    assert "contextSource: 'dom-html-fallback'" in source
    assert "visibleText" in source
    assert "renderedHtml" in source


def test_vibedesk_bridge_supports_manifest_actions_and_context() -> None:
    source = BRIDGE_JS.read_text(encoding="utf-8")

    assert "vibedesk:hello" in source
    assert "vibedesk:init" in source
    assert "vibedesk:ack" in source
    assert "vibedesk:action-request" in source
    assert "vibedesk:action-result" in source
    assert "vibedesk:context-request" in source
    assert "vibedesk:copilot-open" in source


def test_deepsee_ai_and_news_handoff_to_the_active_runtime_when_embedded() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="newsBatchAnalyzeBtn"' in source
    assert "requestAgentInsight" in source
    assert "bridge.requestAgent" in source
    assert "deepsee.insights.analyze" not in source
    assert "deepsee.news.batch-analyze" not in source
    assert "Desk Agent" not in source
    assert 'id="settings-agent"' not in source
    assert "/api/ai/desk-agent/capabilities" not in source


def test_deepsee_agent_analysis_uses_bounded_page_evidence() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")
    insight_source = source.split("async function requestAgentInsight", 1)[1].split(
        "let lastAnalyzedMessages", 1
    )[0]
    news_source = source.split("async function runNewsBatchAnalysis", 1)[1].split(
        "function bindNewsEngineControls", 1
    )[0]

    assert ".slice(0, 30)" in insight_source
    assert ".slice(0, 180)" in insight_source
    assert "不扫描项目、数据库或其他文件" in insight_source
    assert "当前筛选无样本" in insight_source
    assert "页面结构化 Context、当前 DOM/HTML 已同步" in insight_source
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
