from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.main import create_app
from app.services import send_dispatcher


INDEX_HTML = Path(PROJECT_ROOT) / "static" / "index.html"


def test_send_provider_is_locked_to_wechatapi():
    assert send_dispatcher.get_send_provider() == "wechatapi_gateway"
    assert send_dispatcher.get_send_provider("wechatpad_direct") == "wechatapi_gateway"
    assert send_dispatcher.get_send_provider("langbot_gateway") == "wechatapi_gateway"


def test_legacy_wechatpad_write_route_is_not_mounted():
    paths = {getattr(route, "path", "") for route in create_app().routes}
    assert "/api/send/wechatpad" not in paths
    assert not any(path.startswith("/api/wechat8061") for path in paths)


def test_frontend_exposes_only_wechatapi_send_channel():
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert 'option value="wechatapi_gateway"' in source
    assert 'option value="wechatpad_direct"' not in source
    assert "function getSendProvider(){\n\t            return 'wechatapi_gateway';" in source
    assert "通讯录与发送统一使用 WeChatAPI" in source
    assert "chatlog 兜底" not in source
    assert "/api/wechat8061/" not in source
    assert "refreshWechat8061SyncStatus" not in source
    assert "'/api/contacts?include_labels=1&wechatapi_only=1'" in source
    assert "'/api/chats?wechatapi_only=1'" in source


def test_capabilities_only_advertise_wechatapi():
    response = TestClient(create_app()).get("/api/send/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["current"]["provider"] == "wechatapi_gateway"
    assert [item["provider"] for item in body["providers"]] == ["wechatapi_gateway"]
