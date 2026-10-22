"""Real routes/stores with synthetic Mod sessions, never real account data."""
import time
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api.website_auth import COOKIE, DESK_ORIGIN, Identity
from tests.mod_storage.test_routes import _manifest, _publish, _session_headers
from tests.market_alerts.test_market_alert_routes import alert_payload


@pytest.fixture
def api(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db", runtime_dir=tmp_path,
                        enable_domain_suites=False, _env_file=None)
    with TestClient(create_app(settings, data_services=[]), base_url=DESK_ORIGIN) as client:
        _publish(client, _manifest("market-daily"))
        yield client


def headers(api, **kwargs):
    return _session_headers(api, module_id="market-daily", **kwargs)


def test_signed_watchlist_owner_cannot_be_changed_by_headers(api):
    owner = headers(api)
    forged = {**owner, "X-User-Id": "victim", "X-Workspace-Id": "victim"}
    result = api.put("/api/watchlists", headers=forged, json={
        "revision": 0, "groups": [{"id": "private", "name": "账户 A 自选", "symbols": []}],
    })
    assert result.status_code == 200, result.text
    assert result.json()["userId"] == "user-a"
    assert result.json()["workspaceId"] == "workspace-a"
    assert result.headers["cache-control"] == "private, no-store"
    assert api.get("/api/watchlists", headers=owner).json()["revision"] == 1
    for other in (headers(api, user_id="user-b"), headers(api, workspace_id="workspace-b")):
        result = api.get("/api/watchlists", headers=other)
        assert result.json()["revision"] == 0
        assert result.json()["groups"][0]["id"] == "sample"
    assert api.put("/api/watchlists", headers=owner, json={
        "revision": 0, "groups": [{"id": "stale", "name": "旧数据", "symbols": []}],
    }).status_code == 409


def test_signed_alerts_crud_and_foreign_id_isolation(api):
    owner = headers(api)
    created = api.post("/api/market-alerts", headers=owner, json=alert_payload())
    assert created.status_code == 201
    item = created.json()
    assert item["userId"] == "user-a"
    for other in (headers(api, user_id="user-b"), headers(api, workspace_id="workspace-b")):
        assert api.get("/api/market-alerts", headers=other).json()["items"] == []
        assert api.patch(f"/api/market-alerts/{item['id']}", headers=other, json={"price": 1}).status_code == 404
        assert api.delete(f"/api/market-alerts/{item['id']}", headers=other).status_code == 404
    assert api.patch(f"/api/market-alerts/{item['id']}", headers=owner, json={"enabled": False}).status_code == 200
    assert api.get("/api/market-alerts?enabled=true", headers=owner).json()["items"] == []
    assert api.delete(f"/api/market-alerts/{item['id']}", headers=owner).status_code == 200


@pytest.mark.parametrize("method,path,payload", [
    ("PUT", "/api/watchlists", {"revision": 0, "groups": []}),
    ("POST", "/api/watchlists/groups", {"id": "core", "name": "核心"}),
    ("PATCH", "/api/watchlists/groups/sample", {"name": "核心"}),
    ("DELETE", "/api/watchlists/groups/sample", None),
    ("PUT", "/api/watchlists/groups/sample/securities/US/AAPL", {"symbol": "AAPL", "name": "Apple", "market": "US"}),
    ("DELETE", "/api/watchlists/groups/sample/securities/US/AAPL", None),
    ("POST", "/api/market-alerts", alert_payload()),
    ("PATCH", "/api/market-alerts/foreign", {"price": 2}),
    ("DELETE", "/api/market-alerts/foreign", None),
])
def test_read_only_session_cannot_mutate_any_storage_route(api, method, path, payload):
    manifest = _manifest("market-daily")
    manifest.pop("storage")
    manifest["permissions"] = ["storage.read"]
    _publish(api, manifest)
    signed = headers(api)
    assert api.get("/api/watchlists", headers=signed).status_code == 200
    assert api.get("/api/market-alerts", headers=signed).status_code == 200
    assert api.request(method, path, headers=signed, json=payload).status_code == 403


def test_missing_grant_wrong_mod_and_stale_revision_are_rejected(api):
    original = headers(api)
    manifest = _manifest("market-daily")
    manifest.pop("storage")
    manifest["permissions"] = ["market.read"]
    _publish(api, manifest)
    for signed in (original, headers(api)):
        for path in ("/api/watchlists", "/api/market-alerts"):
            assert api.get(path, headers=signed).status_code == 403
    _publish(api, _manifest("research-notes"))
    unrelated = _session_headers(api)
    assert api.get("/api/watchlists", headers=unrelated).status_code == 403
    assert api.get("/api/market-alerts", headers=unrelated).status_code == 403


def test_bad_credentials_and_instance_never_fall_back_to_local_identity(api):
    signed = headers(api)
    for path in ("/api/watchlists", "/api/market-alerts"):
        assert api.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401
        assert api.get(path, headers={"Authorization": signed["Authorization"]}).status_code == 403
        assert api.get(path, headers={**signed, "X-Newma-Desk-Instance-Id": "other"}).status_code == 403
        assert api.get(path, headers={**signed, "X-Newma-Dock-Instance-Id": "other"}).status_code == 400


@pytest.mark.parametrize("module_id", ["news-radar", "catalyst-calendar"])
def test_news_and_calendar_only_read_shared_watchlists(api, module_id):
    _publish(api, _manifest(module_id))
    signed = _session_headers(api, module_id=module_id)
    assert api.get("/api/watchlists", headers=signed).status_code == 200
    assert api.post("/api/watchlists/groups", headers=signed, json={"id": "extra", "name": "不应写入"}).status_code == 403
    assert api.get("/api/market-alerts", headers=signed).status_code == 403


def test_website_cookie_requires_mod_grant_and_bound_sessions_revoke(api):
    signed = headers(api, user_id="cloud-user", workspace_id="newma-cloud-user-c10375")
    auth = api.app.state.website_auth
    auth.enabled = True
    revoked = False

    async def verify(token):
        if revoked or token != "synthetic-website-session":
            raise HTTPException(401, "synthetic revoked")
        return Identity("cloud-user", "newma-cloud-user-c10375", time.time() + 600)

    auth.verify = verify
    claims = api.app.state.mod_session_service.validate(signed["Authorization"].removeprefix("Bearer "))
    api.cookies.set(COOKIE, "synthetic-website-session")
    for path in ("/api/watchlists", "/api/market-alerts"):
        assert api.get(path).status_code == 401  # A login is not a Mod storage grant.
        assert api.get(path, headers=signed).status_code == 401  # Unbound session.
    auth.bind(claims, "synthetic-website-session")
    for path in ("/api/watchlists", "/api/market-alerts"):
        result = api.get(path, headers=signed)
        assert result.status_code == 200, result.text
        assert result.headers["cache-control"] == "private, no-store"
        assert api.get(path, headers={**signed, "X-User-Id": "victim"}).status_code == 403
    assert api.post("/api/market-alerts", headers=signed, json=alert_payload()).status_code == 403
    created = api.post("/api/market-alerts", headers={**signed, "Origin": DESK_ORIGIN}, json=alert_payload())
    assert created.status_code == 201, created.text
    revoked = True
    for path in ("/api/watchlists", "/api/market-alerts"):
        assert api.get(path, headers=signed).status_code == 401


@pytest.mark.parametrize("module_id", ["market-daily", "market-technical", "multi-timeframe", "relative-strength", "event-timeline", "trading-replay"])
def test_real_market_manifests_grant_storage_and_separate_alert_writes(api, module_id):
    root = Path(__file__).resolve().parents[4]
    definition = json.loads((root / "mods" / module_id / "mod.json").read_text())
    manifest = {**definition["manifest"], **{key: definition[key] for key in ("id", "name", "version")},
                "entry": definition["runtime"]["entry"]}
    assert manifest["actions"]["market.set-alert"]["permission"] == "storage.write"
    assert "market-data" in manifest["dataServices"]
    _publish(api, manifest)
    signed = _session_headers(api, module_id=module_id)
    created = api.post("/api/market-alerts", headers=signed, json=alert_payload())
    assert created.status_code == 201, created.text
    item = created.json()
    assert api.get("/api/market-alerts", headers=signed).json()["items"][0]["id"] == item["id"]
    assert api.delete(f"/api/market-alerts/{item['id']}", headers=signed).status_code == 200
