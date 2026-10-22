"""Synthetic accounts and temporary stores only; no real replay migration."""
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


SPEC = {"moduleId": "trading-replay", "title": "私有模拟回放", "security": {"symbol": "AAPL", "name": "Apple", "market": "US"},
        "timeframe": "1d", "cursor": 1, "totalBars": 2, "orders": []}
BASE = "/api/artifacts/replays"


@pytest.fixture
def api(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db", runtime_dir=tmp_path,
                        enable_domain_suites=False, _env_file=None)
    with TestClient(create_app(settings, data_services=[]), base_url=DESK_ORIGIN) as client:
        _publish(client, _manifest("trading-replay"))
        yield client


def signed(api, **kw):
    return _session_headers(api, module_id="trading-replay", **kw)


def test_replays_are_private_to_signed_user_and_workspace_and_do_not_adopt_legacy(api):
    legacy = api.post(BASE, json=SPEC).json()
    owner = signed(api)
    assert api.get(BASE + "?module_id=trading-replay", headers=owner).json() == []
    item = api.post(BASE, headers={**owner, "X-User-Id": "victim"}, json=SPEC)
    assert item.status_code == 201, item.text
    assert item.headers["cache-control"] == "private, no-store"
    assert item.json()["userId"] == "user-a"
    item = item.json()
    for other in (signed(api, user_id="user-b"), signed(api, workspace_id="workspace-b")):
        assert api.get(BASE + "?module_id=trading-replay", headers=other).json() == []
        for suffix in ("", "/view"):
            assert api.get(BASE + f"/{item['id']}" + suffix, headers=other).status_code == 404
        assert api.post(BASE + f"/{item['id']}/publish", headers=other).status_code == 404
    assert api.get(BASE + f"/{legacy['id']}/view", headers=owner).status_code == 404
    assert api.get(BASE + f"/{item['id']}/view").status_code == 404
    assert api.post(BASE + f"/{item['id']}/publish", headers=owner).status_code == 200
    view = api.get(BASE + f"/{item['id']}/view", headers=owner)
    assert view.status_code == 200
    assert view.headers["cache-control"] == "private, no-store"
    assert 'http-equiv="Content-Security-Policy"' in view.text
    assert api.get(BASE + "/latest?module_id=trading-replay", headers=owner).json()["id"] == item["id"]


def test_replay_permissions_instances_revisions_and_module_boundary(api):
    owner = signed(api)
    item = api.post(BASE, headers=owner, json=SPEC).json()
    for bad in ({"Authorization": "Bearer invalid"}, {**owner, "X-Newma-Desk-Instance-Id": "wrong"}):
        assert api.get(BASE + "?module_id=trading-replay", headers=bad).status_code in {401, 403}
    assert api.post(BASE, headers=owner, json={**SPEC, "moduleId": "market-daily"}).status_code == 404
    _publish(api, _manifest("market-daily"))
    unrelated = _session_headers(api, module_id="market-daily")
    assert api.get(BASE + f"/{item['id']}", headers=unrelated).status_code == 403
    manifest = _manifest("trading-replay")
    manifest.pop("storage")
    manifest["permissions"] = ["storage.read"]
    _publish(api, manifest)
    assert api.get(BASE + f"/{item['id']}", headers=owner).status_code == 403
    readonly = signed(api)
    assert api.get(BASE + f"/{item['id']}/view", headers=readonly).status_code == 200
    assert api.post(BASE, headers=readonly, json=SPEC).status_code == 403
    assert api.post(BASE + f"/{item['id']}/publish", headers=readonly).status_code == 403


def test_replay_website_binding_and_revocation(api):
    owner = signed(api, user_id="cloud", workspace_id="newma-cloud-c10375")
    auth = api.app.state.website_auth
    auth.enabled = True
    revoked = False
    async def verify(token):
        if revoked or token != "synthetic-session":
            raise HTTPException(401)
        return Identity("cloud", "newma-cloud-c10375", time.time() + 600)
    auth.verify = verify
    api.cookies.set(COOKIE, "synthetic-session")
    assert api.get(BASE + "?module_id=trading-replay").status_code == 401
    assert api.get(BASE + "?module_id=trading-replay", headers=owner).status_code == 401
    claims = api.app.state.mod_session_service.validate(owner["Authorization"].removeprefix("Bearer "))
    auth.bind(claims, "synthetic-session")
    assert api.post(BASE, headers=owner, json=SPEC).status_code == 403
    created = api.post(BASE, headers={**owner, "Origin": DESK_ORIGIN}, json=SPEC)
    assert created.status_code == 201, created.text
    path = created.json()["viewUrl"]
    assert api.get(path).status_code == 401
    assert api.get(path, headers=owner).status_code == 200
    revoked = True
    assert api.get(path, headers=owner).status_code == 401


@pytest.mark.parametrize("module_id", ["market-technical", "multi-timeframe", "relative-strength", "event-timeline", "trading-replay"])
def test_real_layout_manifests_have_private_namespace_and_write_action(api, module_id):
    root = Path(__file__).resolve().parents[4]
    definition = json.loads((root / "mods" / module_id / "mod.json").read_text())
    manifest = {**definition["manifest"], **{key: definition[key] for key in ("id", "name", "version")}, "entry": definition["runtime"]["entry"]}
    assert manifest["actions"]["workspace.save-layout"]["permission"] == "storage.write"
    _publish(api, manifest)
    owner = _session_headers(api, module_id=module_id)
    path = f"/api/mods/{module_id}/storage/layouts/test-layout"
    result = api.put(path, headers=owner, json={"expectedRevision": 0, "value": {"name": "私人布局"}})
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "private, no-store"
    assert api.get(path, headers=owner).status_code == 200
    assert api.get(path, headers=_session_headers(api, module_id=module_id, user_id="other")).status_code == 404
    assert api.put(path, headers=owner, json={"expectedRevision": 0, "value": {}}).status_code == 409


@pytest.mark.parametrize("module_id", ["news-radar", "catalyst-calendar"])
def test_real_research_readers_can_read_shared_watchlists_but_not_edit(api, module_id):
    root = Path(__file__).resolve().parents[4]
    definition = json.loads((root / "mods" / module_id / "mod.json").read_text())
    runtime = definition["runtime"]
    manifest = {**definition["manifest"], **{key: definition[key] for key in ("id", "name", "version")},
                "entry": {"type": "external", "url": runtime["defaultBaseUrl"] + runtime["route"]}}
    _publish(api, manifest)
    headers = _session_headers(api, module_id=module_id)
    result = api.get("/api/watchlists", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["userId"] == "user-a"
    assert result.headers["cache-control"] == "private, no-store"
    assert api.put("/api/watchlists", headers=headers, json={"revision": 0, "groups": []}).status_code == 403
