from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.config import settings
from app.db import Base
from app.main import create_app
from app.models import Chat, Contact, Message, SyncState
from app.routers import wechat_gateway as wechat_gateway_router

ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "static" / "index.html"
API_HEADERS = ({"X-API-Token": str(settings.API_TOKEN).strip()} if str(getattr(settings, "API_TOKEN", "") or "").strip() else {})


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "wechat-gateway-frontend.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(
        engine,
        tables=[
            Chat.__table__,
            Contact.__table__,
            Message.__table__,
            SyncState.__table__,
        ],
    )
    return TestingSession


def _client(tmp_path: Path) -> TestClient:
    Session = _session_factory(tmp_path)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    return TestClient(app)


def test_send_settings_include_wechat_gateway_panel_and_option():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert 'option value="wechatapi_gateway"' in source
    assert 'id="sendProviderWechatApi"' in source
    assert 'id="wechatGatewayEnabled"' in source
    assert 'id="wechatGatewayOutboundEnabled"' in source
    assert 'id="wechatGatewayRuleSummary"' in source
    assert 'id="wechatGatewayDelayMin"' in source
    assert 'id="wechatGatewayDelayMax"' in source
    assert 'id="wechatTriggerRegexpPatterns"' in source
    assert 'id="wechatTriggerAtMentionEnabled"' in source
    assert 'id="wechatTriggerRandomRate"' in source
    assert 'id="wechatTriggerPrivateWakeupWindowSeconds"' in source
    assert 'id="wechatTriggerPrivateWakeupWhitelistEnabled"' in source
    assert 'id="wechatTriggerPrivateWakeupWhitelistChatIds"' in source
    assert 'id="wechatTriggerPrivateWakeupExitCommands"' in source
    assert 'id="wechatGatewaySessionizedReplyEnabled"' in source
    assert 'id="wechatGatewayFixedSubsessionEnabled"' in source
    assert 'id="wechatGatewayFixedSubsessionId"' in source
    assert 'id="wechatGatewayFixedSubsessionName"' in source
    assert 'id="wechatGatewayAutoLearnSubsessionMembers"' in source
    assert 'id="wechatSubsessionSystemPrompt"' in source
    assert 'id="wechatSubsessionModelRouteKind"' in source
    assert 'id="wechatSubsessionModelRouteKey"' in source
    assert 'id="wechatSubsessionModelOverride"' in source
    assert 'id="wechatSubsessionHistoryMaxMessages"' in source
    assert 'id="wechatSubsessionHistoryMaxTokens"' in source
    assert 'saveWechatGatewayConfig(' in source
    assert 'loadWechatGatewayConfig(' in source
    assert 'testWechatGatewayHealth(' in source
    assert "'/api/wechat-gateway/bind-callback'" in source
    assert 'option value="langbot_gateway"' not in source
    assert 'id="sendProviderLangbot"' not in source


def test_send_provider_js_handles_wechat_gateway_visibility_and_config_load():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert "return 'wechatapi_gateway';" in source
    assert "const pWechatApi = document.getElementById('sendProviderWechatApi');" in source
    assert "pWechatApi.classList.remove('hidden');" in source
    assert "pWechatApi.style.display = '';" in source
    assert 'option value="wechatpad_direct"' not in source
    assert "await loadWechatGatewayConfig();" in source
    assert "outbound_random_delay_min_seconds" in source
    assert "outbound_random_delay_max_seconds" in source
    assert "normalizeWechatGatewayCallbackUrl" in source
    assert "保存时自动补 /api/wechat-gateway/callback" in source
    assert "msg.textContent = '回调已绑定：' + String(res?.callback_url || callbackUrl);" in source
    assert "sessionized_reply_enabled" in source
    assert "fixed_subsession_enabled" in source
    assert "fixed_subsession_id" in source
    assert "auto_learn_subsession_members" in source
    assert "private_wakeup_window_seconds" in source
    assert "private_wakeup_whitelist_enabled" in source
    assert "private_wakeup_whitelist_chat_ids" in source
    assert "private_wakeup_exit_commands" in source
    assert "loadWechatGatewaySubsessionConfig" in source
    assert "saveWechatGatewaySubsessionConfig" in source
    assert "'/api/wechat-gateway/subsession-config/'" in source
    assert "wechatSubsessionSystemPrompt" in source
    assert "wechatSubsessionModelRouteKind" in source
    assert "wechatSubsessionModelRouteKey" in source
    assert "wechatSubsessionModelOverride" in source
    assert "wechatSubsessionHistoryMaxMessages" in source
    assert "wechatSubsessionHistoryMaxTokens" in source
    assert "sendProviderLangbot" not in source
    assert "loadLangbotBots(" not in source
    assert "fillGatewayBotUuidFromLangbot(" not in source
    assert "importLangbotBotToDirect(" not in source
    assert "testLangbotGatewayHealth(" not in source


def test_wechat_gateway_config_api_roundtrip(tmp_path):
    client = _client(tmp_path)
    payload = {
        "enabled": True,
        "outbound_enabled": True,
        "callback_public_url": "http://example.test/wechat/callback",
        "allow_chat_ids": ["filehelper"],
        "keyword_blocklist": ["广告"],
        "outbound_random_delay_min_seconds": 3,
        "outbound_random_delay_max_seconds": 5,
    }

    saved = client.post("/api/wechat-gateway/config", json=payload, headers=API_HEADERS)
    assert saved.status_code == 200
    body = saved.json()
    assert body["status"] == "ok"
    assert body["config"]["enabled"] is True
    assert body["config"]["allow_chat_ids"] == ["filehelper"]

    loaded = client.get("/api/wechat-gateway/config", headers=API_HEADERS)
    assert loaded.status_code == 200
    data = loaded.json()
    assert data["enabled"] is True
    assert data["outbound_enabled"] is True
    assert data["callback_public_url"] == "http://example.test/wechat/callback"
    assert data["keyword_blocklist"] == ["广告"]
    assert data["outbound_random_delay_min_seconds"] == 3
    assert data["outbound_random_delay_max_seconds"] == 5


def test_wechat_gateway_trigger_rules_roundtrip_includes_private_wakeup_fields(tmp_path):
    client = _client(tmp_path)
    payload = {
        "enabled": True,
        "smart_reply_enabled": True,
        "group_enabled": True,
        "private_enabled": True,
        "prefixes": ["ai"],
        "private_wakeup_window_seconds": 240,
        "private_wakeup_whitelist_enabled": True,
        "private_wakeup_whitelist_chat_ids": ["wxid_a", "wxid_b"],
        "private_wakeup_exit_commands": ["暂停", "结束"],
        "min_text_length": 2,
    }

    saved = client.post("/api/wechat-gateway/trigger-rules", json=payload, headers=API_HEADERS)
    assert saved.status_code == 200
    body = saved.json()
    assert body["status"] == "ok"
    assert body["rules"]["private_wakeup_window_seconds"] == 240
    assert body["rules"]["private_wakeup_whitelist_enabled"] is True
    assert body["rules"]["private_wakeup_whitelist_chat_ids"] == ["wxid_a", "wxid_b"]
    assert body["rules"]["private_wakeup_exit_commands"] == ["暂停", "结束"]

    loaded = client.get("/api/wechat-gateway/trigger-rules", headers=API_HEADERS)
    assert loaded.status_code == 200
    data = loaded.json()
    assert data["private_wakeup_window_seconds"] == 240
    assert data["private_wakeup_whitelist_enabled"] is True
    assert data["private_wakeup_whitelist_chat_ids"] == ["wxid_a", "wxid_b"]
    assert data["private_wakeup_exit_commands"] == ["暂停", "结束"]


def test_wechat_gateway_callback_route_is_api_auth_exempt(tmp_path):
    client = _client(tmp_path)
    payload = {
        "TypeName": "Offline",
        "Appid": "wx_app_test",
        "Data": {},
    }

    response = client.post("/api/wechat-gateway/callback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["reason"] == "ignored_event"
    assert data["event_type"] == "Offline"
