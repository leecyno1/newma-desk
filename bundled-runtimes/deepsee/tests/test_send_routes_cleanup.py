from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.config import settings
from app.main import create_app
from app.routers import send

API_HEADERS = ({"X-API-Token": str(settings.API_TOKEN).strip()} if str(getattr(settings, "API_TOKEN", "") or "").strip() else {})


def test_send_capabilities_no_longer_lists_langbot_provider():
    client = TestClient(create_app())

    response = client.get("/api/send/capabilities", headers=API_HEADERS)

    assert response.status_code == 200
    data = response.json()
    providers = [str(item.get("provider") or "") for item in data.get("providers", [])]
    assert "langbot_gateway" not in providers
    assert "wechatapi_gateway" in providers


def test_send_langbot_routes_are_absent_from_app():
    app = create_app()
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/send/langbot" not in paths
    assert "/api/send/langbot/health" not in paths
    assert "/api/send/langbot/bots" not in paths
    assert "/api/langbot/bots" not in paths
    assert "/api/sync/langbot" not in paths


def test_send_out_ignores_removed_provider_config_and_uses_wechatapi(monkeypatch):
    monkeypatch.setattr(
        send,
        "dispatch_send_items",
        lambda items, request=None: {
            "status": "ok",
            "provider": "wechatapi_gateway",
            "results": [{"ok": True, "target": items[0].target}],
        },
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/send/out",
        json={"items": [{"target": "filehelper", "text": "hello"}]},
        headers=API_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] == "wechatapi_gateway"
