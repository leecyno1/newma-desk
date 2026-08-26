from __future__ import annotations

from collections import Counter

import os
import sys

from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.config import settings
from app.main import create_app

_AGENT_TOKEN = str(getattr(settings, "AGENT_API_TOKEN", "") or "").strip()
_AGENT_TOKENS = [v.strip() for v in str(getattr(settings, "AGENT_API_TOKENS", "") or "").split(",") if v.strip()]
_AGENT_HEADER_TOKEN = _AGENT_TOKEN or (_AGENT_TOKENS[0] if _AGENT_TOKENS else "")
API_HEADERS = ({"X-Agent-Token": _AGENT_HEADER_TOKEN} if _AGENT_HEADER_TOKEN else {})


def test_agent_modules_do_not_advertise_langbot_send_or_sync_routes():
    client = TestClient(create_app())

    response = client.get("/api/agent/modules", headers=API_HEADERS)

    assert response.status_code == 200
    items = response.json()["items"]
    sending = next(item for item in items if item["module"] == "sending")
    syncing = next(item for item in items if item["module"] == "sync_and_backup")

    assert "/api/send/langbot" not in sending["apis"]
    assert "/api/sync/langbot" not in syncing["apis"]


def test_agent_openapi_paths_do_not_include_removed_langbot_routes():
    client = TestClient(create_app())

    response = client.get("/api/agent/openapi", headers=API_HEADERS)

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/send/langbot" not in paths
    assert "/api/send/langbot/health" not in paths
    assert "/api/send/langbot/bots" not in paths
    assert "/api/sync/langbot" not in paths
    assert "/api/langbot/bots" not in paths


def test_app_does_not_register_duplicate_route_methods():
    app = create_app()
    route_keys = [
        (
            str(getattr(route, "path", "")),
            tuple(sorted(getattr(route, "methods", set()) or set())),
        )
        for route in app.routes
    ]

    duplicates = {key: count for key, count in Counter(route_keys).items() if count > 1}

    assert duplicates == {}
