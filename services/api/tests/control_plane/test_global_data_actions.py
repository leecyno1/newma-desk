"""The global page and its declared read actions must use one domain runtime."""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.data_services.models import DataServiceDescriptor
from vibe_visualization_api.main import create_app
from tests.mod_storage.test_routes import _publish, _session_headers

ROOT = Path(__file__).resolve().parents[4]
READS = [
    ("global-intel.snapshot", "world-intel", "/api/global-intel/overview"),
    ("global-intel.static-map", "world-intel", "/api/global-intel/static"),
    ("crucix.snapshot", "crucix", "/api/crucix/snapshot"),
    ("crucix.health", "crucix", "/api/crucix/health"),
]
HTTP_CLIENT = httpx.AsyncClient


def payload(action):
    value = {"runtimeEvidence": "independent-candidate"}
    if action == "crucix.snapshot":
        value.update(contract="newma-desk.crucix-intelligence.v1", freshness={}, sourceHealth={},
                     news=[], macro={}, **{"global": {}}, newsCoverage={"coverage": {"succeeded": 18, "failed": 1}})
    if action == "crucix.health":
        value.update(contract="newma-desk.crucix-health.v1", status="degraded", service="crucix", sourceHealth={})
    return value


def host(tmp_path, monkeypatch, *, independent=True, module_id="global-situation"):
    descriptors = [DataServiceDescriptor.model_validate(json.loads((ROOT / f"integrations/{name}/data-service.json").read_text()))
                   for name in ("world-intel", "crucix")]
    app = create_app(Settings(_env_file=None, runtime_dir=tmp_path, database_path=tmp_path / "host.sqlite3",
        mod_store_dir=tmp_path / "mods", enable_domain_suites=False, enable_workflow_runtime_worker=False,
        global_intelligence_api_url="http://127.0.0.1:18952" if independent else ""), data_services=descriptors)
    client = TestClient(app)
    raw = json.loads((ROOT / "mods/global-situation/mod.json").read_text())
    manifest = {**raw["manifest"], "id": module_id, "name": raw["name"], "version": raw["version"],
                "entry": raw["runtime"]["entry"]}
    _publish(client, manifest)
    headers = _session_headers(client, module_id=module_id)
    legacy_calls, upstream_calls = [], []

    async def legacy(service, capability, input_data, **kwargs):
        legacy_calls.append(capability)
        return {**payload(capability), "runtimeEvidence": "embedded-old"}

    app.state.data_service_client.invoke = legacy
    factory = HTTP_CLIENT
    def upstream(request):
        upstream_calls.append(request)
        action = next(action for action, _, path in READS if path == request.url.path)
        assert request.method == "GET" and request.content == b""
        assert request.headers["authorization"] == headers["Authorization"]
        assert request.headers["x-newma-desk-instance-id"] == headers["X-Newma-Desk-Instance-Id"]
        assert "cookie" not in request.headers and "x-user-id" not in request.headers
        return httpx.Response(200, json=payload(action))

    import vibe_visualization_api.global_intelligence_proxy as proxy
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **kwargs: factory(transport=httpx.MockTransport(upstream), **kwargs))
    return client, headers, legacy_calls, upstream_calls


@pytest.mark.parametrize("action,service,path", READS)
def test_independent_global_action_matches_page_without_embedded_parser(tmp_path, monkeypatch, action, service, path):
    client, headers, legacy, upstream = host(tmp_path, monkeypatch)
    page = client.get(path, headers=headers)
    assert page.status_code == 200
    response = client.post(f"/api/mods/global-situation/actions/{action}",
        headers={**headers, "Cookie": "must-not-forward", "X-User-Id": "forged"}, json={})
    assert response.status_code == 200, response.text
    assert response.json() == page.json()
    assert not legacy
    assert len(upstream) == 2


@pytest.mark.parametrize("independent,module_id", [(False, "global-situation"), (True, "macro-monitor")])
def test_default_mode_and_other_modules_keep_their_existing_provider(tmp_path, monkeypatch, independent, module_id):
    client, headers, legacy, upstream = host(tmp_path, monkeypatch, independent=independent, module_id=module_id)
    response = client.post(f"/api/mods/{module_id}/actions/crucix.snapshot", headers=headers, json={})
    assert response.status_code == 200 and response.json()["runtimeEvidence"] == "embedded-old"
    assert legacy == ["crucix.snapshot"] and not upstream


@pytest.mark.parametrize("status,body", [(403, {"private": "grant"}), (503, {"private": "failure"}), (200, [])])
def test_independent_action_failure_never_falls_back_or_retries(tmp_path, monkeypatch, status, body):
    client, headers, legacy, upstream = host(tmp_path, monkeypatch)
    import vibe_visualization_api.global_intelligence_proxy as proxy
    factory = HTTP_CLIENT
    calls = []
    def failed(request):
        calls.append(request)
        return httpx.Response(status, json=body)
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **kw: factory(transport=httpx.MockTransport(failed), **kw))
    response = client.post("/api/mods/global-situation/actions/crucix.snapshot", headers=headers, json={})
    assert response.status_code == (403 if status == 403 else 503)
    assert "private" not in response.text and len(calls) == 1 and not legacy


def test_invalid_grants_inputs_and_changed_provider_are_not_forwarded(tmp_path, monkeypatch):
    client, headers, legacy, upstream = host(tmp_path, monkeypatch)
    endpoint = "/api/mods/global-situation/actions/crucix.snapshot"
    assert client.post(endpoint, json={}).status_code == 401
    assert client.post(endpoint, headers={**headers, "X-Newma-Desk-Instance-Id": "other"}, json={}).status_code == 403
    assert client.post(endpoint, headers=headers, json={"url": "http://outside.invalid"}).status_code == 422
    service = client.app.state.data_service_registry.get("crucix")
    service.capabilities["crucix.snapshot"].path = "/api/unexpected"
    assert client.post(endpoint, headers=headers, json={}).status_code == 403
    assert not legacy and not upstream


def test_website_action_rechecks_bound_identity_and_revocation(tmp_path, monkeypatch):
    from tests.test_website_auth import global_cloud_client, COOKIE, TOKEN, WORKSPACE, DESK_ORIGIN
    from vibe_visualization_api.data_services.registry import DataServiceRegistry
    import vibe_visualization_api.global_intelligence_proxy as proxy
    client, authority, headers = global_cloud_client(tmp_path)
    client.app.state.global_intelligence_settings.global_intelligence_api_url = "http://127.0.0.1:18952"
    repository = client.app.state.resolve_module_repository()
    current = repository.get_published("global-situation")
    raw = json.loads((ROOT / "mods/global-situation/mod.json").read_text())
    draft = repository.create_draft({**current.manifest, "actions": raw["manifest"]["actions"]})
    repository.publish(draft.module_id, draft.revision)
    client.app.state.data_service_registry = DataServiceRegistry([DataServiceDescriptor.model_validate(
        json.loads((ROOT / "integrations/crucix/data-service.json").read_text()))])
    client.cookies.set(COOKIE, TOKEN)
    issued = client.post("/api/mods/global-situation/sessions", headers={"Origin": DESK_ORIGIN},
        json={"instanceId": "global-one", "workspaceId": WORKSPACE})
    assert issued.status_code == 201, issued.text
    client.cookies.clear()
    headers["Authorization"] = "Bearer " + issued.json()["accessToken"]
    calls = []
    def upstream(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=payload("crucix.snapshot"))
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **kw: HTTP_CLIENT(transport=httpx.MockTransport(upstream), **kw))
    endpoint = "/api/mods/global-situation/actions/crucix.snapshot"
    response = client.post(endpoint, headers=headers, json={})
    assert response.status_code == 200, response.text
    assert calls == ["/api/crucix/snapshot"]
    authority.state.revoked = True
    client.app.state.website_auth.cache.clear()
    assert client.post(endpoint, headers=headers, json={}).status_code == 401
    assert calls == ["/api/crucix/snapshot"]
