from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_wechat_gateway_agent_websocket_route_accepts_non_wechat_without_affecting_user_channels():
    client = TestClient(app)
    with client.websocket_connect("/api/wechat-gateway/ws/agent") as ws:
        ws.send_json({"channel": "main", "source": "hermes", "message_id": "ws-main-1", "chat_id": "terminal", "text": "hi"})
        payload = ws.receive_json()
    assert payload["stored"] is False
    assert payload["reason"] == "non_wechat_channel"
