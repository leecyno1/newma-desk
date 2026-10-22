import json
from pathlib import Path

from tests.mod_storage.test_routes import client, _manifest, _publish, _session_headers


def industry_manifest():
    suite = json.loads((Path(__file__).resolve().parents[4] / "mods/research-industry-suite/suite.json").read_text())
    page = next(page for page in suite["pages"] if page["id"] == "industry-map")
    manifest = _manifest("industry-map")
    manifest["storage"] = page["manifest"]["storage"]
    return manifest


def test_industry_versions_use_signed_scope_and_preserve_conflicting_versions(client, monkeypatch):
    manifest = industry_manifest()
    manifest["permissions"].append("analysis.read")
    _publish(client, manifest)
    owner = _session_headers(client, module_id="industry-map")
    another_workspace = _session_headers(client, module_id="industry-map", workspace_id="workspace-b")
    another_user = _session_headers(client, module_id="industry-map", user_id="user-b")
    endpoint = "/api/mods/industry-map/storage/industry-maps/humanoid"
    value = {"schemaVersion": "newma-desk.industry-map.v1", "sectorKey": "humanoid", "versions": [{"number": 1, "note": "synthetic private evidence"}]}
    assert client.put(endpoint, headers=owner, json={"expectedRevision": 0, "value": value}).status_code == 200
    assert client.get(endpoint, headers=owner).json()["value"] == value
    for headers in (another_user, another_workspace):
        assert client.get(endpoint, headers=headers).status_code == 404
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers={**owner, "X-Newma-Desk-Instance-Id": "wrong"}).status_code == 403
    # Untrusted scope headers cannot override the signed session.
    assert client.get(endpoint, headers={**another_user, "X-User-Id": "user-a", "X-Workspace-Id": "workspace-a"}).status_code == 404
    assert client.put(endpoint, headers=owner, json={"expectedRevision": 0, "value": {"overwrite": True}}).status_code == 409
    assert client.get(endpoint, headers=owner).json()["value"] == value
    assert client.get("/api/artifacts?module_id=industry-map").json() == []
    from vibe_visualization_api import research_sources
    async def source_reader(body):
        return {"status": "readable", "quoteMatch": "found", "claimVerified": False, "sourceUrl": body.url}
    monkeypatch.setattr(research_sources, "read_source", source_reader)
    assert client.post("/api/mods/industry-map/sources/read", headers=owner, json={"url": "https://example.com/", "quote": "synthetic"}).json()["claimVerified"] is False
    manifest["version"] = "1.0.1"
    _publish(client, manifest)
    assert client.get(endpoint, headers=owner).status_code == 403
    revision = next(item["revision"] for item in client.get("/api/mods").json() if item["moduleId"] == "industry-map")
    service = client.app.state.mod_session_service
    token, _ = service.issue(instance_id="instance-a", user_id="user-a", workspace_id="workspace-a", module_id="industry-map", revision=revision, actions=[], permissions=["storage.read"])
    readonly = {"Authorization": "Bearer " + token, "X-Newma-Desk-Instance-Id": "instance-a"}
    assert client.get(endpoint, headers=readonly).json()["value"] == value
    assert client.put(endpoint, headers=readonly, json={"expectedRevision": 1, "value": value}).status_code == 403
    assert client.post("/api/mods/industry-map/sources/read", headers=readonly, json={"url": "https://example.com/"}).status_code == 403
    monkeypatch.setattr(service, "_ttl_seconds", -1)
    expired, _ = service.issue(instance_id="instance-a", user_id="user-a", workspace_id="workspace-a", module_id="industry-map", revision=revision, actions=[], permissions=["storage.read"])
    assert client.get(endpoint, headers={**readonly, "Authorization": "Bearer " + expired}).status_code == 401
