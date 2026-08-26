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


def _client() -> TestClient:
    raise RuntimeError("_client(tmp_path) required for DB isolation")


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "wechat-gateway-settings-modules.db"
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


def test_function_settings_include_standalone_gateway_and_trigger_modules():
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert 'data-nav-target="wechat-gateway-settings"' in source
    assert 'data-nav-target="wechat-trigger-rules"' in source
    assert 'id="wechat-gateway-settings"' in source
    assert 'id="wechat-trigger-rules"' in source
    assert 'id="wechatSmartReplyEnabled"' in source
    assert 'id="wechatTriggerPrefixes"' in source
    assert 'id="wechatTriggerMinTextLength"' in source
    assert 'id="wechatHumanReplySuppressionSeconds"' in source
    assert 'id="wechatTriggerRegexpPatterns"' in source
    assert 'id="wechatTriggerAtMentionEnabled"' in source
    assert 'id="wechatTriggerRandomRate"' in source
    assert 'id="wechatGatewayAllowChatIds"' in source
    assert 'id="wechatGatewayBlockChatIds"' in source
    assert 'id="wechatGatewayAllowChatIdsEnabled"' in source
    assert 'id="wechatGatewayBlockChatIdsEnabled"' in source
    assert 'id="wechatGatewayKeywordBlocklist"' in source
    assert 'id="wechatTriggerWhitelistChatIdsEnabled"' in source
    assert 'id="wechatTriggerBlacklistChatIdsEnabled"' in source
    assert 'id="wechatTriggerWhitelistSenderIdsEnabled"' in source
    assert 'id="wechatTriggerBlacklistSenderIdsEnabled"' in source
    assert 'class="wechat-policy-grid"' in source
    assert 'class="wechat-policy-card"' in source
    assert 'wechatGatewayAllowSenderIds' not in source
    assert 'wechatGatewayBlockSenderIds' not in source


def test_wechat_settings_js_has_separate_loaders_and_savers():
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert 'async function loadWechatGatewayConfig(' in source
    assert 'async function saveWechatGatewayConfig(' in source
    assert 'async function loadWechatTriggerRules(' in source
    assert 'async function saveWechatTriggerRules(' in source
    assert "requestJson('/api/wechat-gateway/trigger-rules'" in source
    assert "setChecked('wechatGatewayAllowChatIdsEnabled'" in source
    assert "setChecked('wechatGatewayBlockChatIdsEnabled'" in source
    assert "setChecked('wechatTriggerWhitelistChatIdsEnabled'" in source
    assert "setChecked('wechatTriggerBlacklistChatIdsEnabled'" in source
    assert "setChecked('wechatTriggerWhitelistSenderIdsEnabled'" in source
    assert "setChecked('wechatTriggerBlacklistSenderIdsEnabled'" in source
    assert 'allow_chat_ids_enabled:' in source
    assert 'block_chat_ids_enabled:' in source
    assert 'whitelist_chat_ids_enabled:' in source
    assert 'blacklist_chat_ids_enabled:' in source
    assert 'whitelist_sender_ids_enabled:' in source
    assert 'blacklist_sender_ids_enabled:' in source
    assert 'wechatGatewayAllowSenderIds' not in source
    assert 'wechatGatewayBlockSenderIds' not in source


def test_wechat_trigger_rules_api_roundtrip(tmp_path):
    client = _client(tmp_path)
    payload = {
        "enabled": True,
        "smart_reply_enabled": True,
        "group_enabled": True,
        "private_enabled": False,
        "prefixes": ["!", "问"],
        "regexp_patterns": [r"^你好"],
        "at_mention_enabled": True,
        "random_rate": 25,
        "whitelist_chat_ids_enabled": True,
        "whitelist_chat_ids": ["room_1@chatroom"],
        "blacklist_sender_ids_enabled": True,
        "blacklist_sender_ids": ["wxid_bad"],
        "min_text_length": 3,
        "human_reply_suppression_seconds": 180,
    }
    saved = client.post('/api/wechat-gateway/trigger-rules', json=payload, headers=API_HEADERS)
    assert saved.status_code == 200
    body = saved.json()
    assert body['status'] == 'ok'
    assert body['rules']['smart_reply_enabled'] is True
    assert body['rules']['private_enabled'] is False
    assert body['rules']['whitelist_chat_ids_enabled'] is True
    assert body['rules']['blacklist_sender_ids_enabled'] is True

    loaded = client.get('/api/wechat-gateway/trigger-rules', headers=API_HEADERS)
    assert loaded.status_code == 200
    data = loaded.json()
    assert data['enabled'] is True
    assert data['smart_reply_enabled'] is True
    assert data['prefixes'] == ['!', '问']
    assert data['regexp_patterns'] == [r'^你好']
    assert data['at_mention_enabled'] is True
    assert data['random_rate'] == 25
    assert data['whitelist_chat_ids_enabled'] is True
    assert data['blacklist_sender_ids_enabled'] is True
    assert data['min_text_length'] == 3


def test_wechat_trigger_and_gateway_switches_render_horizontally():
    source = INDEX_HTML.read_text(encoding='utf-8')
    assert '#wechat-trigger-rules .wechat-core-switches {' in source
    core_block = source.split('#wechat-trigger-rules .wechat-core-switches {', 1)[1].split('}', 1)[0]
    assert 'grid-template-columns: repeat(4' in core_block
    assert 'width: 100%;' in core_block
    core_label_block = source.split('#wechat-trigger-rules .wechat-core-switches label {', 1)[1].split('}', 1)[0]
    assert 'flex-direction: row;' in core_label_block
    assert 'white-space: nowrap;' in core_label_block
    gateway_block = source.split('#wechat-gateway-settings .wechat-gateway-switches {', 1)[1].split('}', 1)[0]
    assert 'grid-template-columns: repeat(2' in gateway_block
    gateway_label_block = source.split('#wechat-gateway-settings .wechat-gateway-switches label {', 1)[1].split('}', 1)[0]
    assert 'flex-direction:row;' in gateway_label_block
    assert 'white-space:nowrap;' in gateway_label_block
    final_override = source.split('确保核心开关横向排列', 1)[1]
    assert '#function-settings #wechat-trigger-rules .config-group.wechat-core-switches' in final_override
    assert 'display: grid !important;' in final_override
    assert 'grid-template-columns: repeat(4, minmax(0, 1fr)) !important;' in final_override
    assert 'flex-direction: row !important;' in final_override
    assert '.config-group.wechat-inline-toggles:not(.wechat-gateway-switches)' in final_override
    assert '.config-group.wechat-inline-toggles:not(.wechat-core-switches)' in final_override
    assert 'flex-wrap: nowrap !important;' in final_override
    assert 'overflow-x: auto !important;' in final_override
