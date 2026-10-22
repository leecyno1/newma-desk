from unittest.mock import AsyncMock
import json
from pathlib import Path
from vibe_visualization_api.data_services.models import DataServiceDescriptor
from vibe_visualization_api.data_services.registry import DataServiceRegistry

from tests.mod_storage.test_routes import client, _manifest, _publish, _session_headers


ENDPOINT = "/api/mods/runtime/instock-scope"


def test_company_statement_routes_require_declared_company_actions(client):
    root = Path(__file__).resolve().parents[4]
    service = DataServiceDescriptor.model_validate_json((root / "integrations/instock-analysis/data-service.json").read_text())
    client.app.state.data_service_registry = DataServiceRegistry([service])
    suite = json.loads((root / "mods/instock-company-suite/suite.json").read_text())
    page = next(page for page in suite["pages"] if page["id"] == "instock-stock-research")
    manifest = _manifest(page["id"])
    manifest.pop("storage")
    manifest["permissions"] = page["manifest"]["permissions"]
    manifest["dataServices"] = page["manifest"]["dataServices"]
    manifest["actions"] = page["manifest"]["actions"]
    _publish(client, manifest)
    company = _session_headers(client, module_id=page["id"])
    publish_chain(client)
    unrelated = _session_headers(client, module_id="instock-industry-chain")
    for suffix in ("statement-announcements", "statement-evidence"):
        target = {"method": "GET", "path": "/api/v1/stock-research/" + suffix}
        assert client.post(ENDPOINT, headers=company, json=target).status_code == 200
        assert client.post(ENDPOINT, headers=unrelated, json=target).status_code == 403
        assert client.post(ENDPOINT, headers=company, json={**target, "method": "POST"}).status_code == 403


def publish_chain(client):
    manifest = _manifest("instock-industry-chain")
    manifest["permissions"].append("analysis.read")
    manifest["dataServices"] = ["instock-analysis"]
    manifest["actions"] = {"analysis.industry-chain": {
        "binding": {"type": "data", "service": "instock-analysis", "capability": "analysis.industry-chain"},
        "execution": "request", "permission": "analysis.read", "confirmation": "none",
        "inputSchema": {"type": "object"}, "outputSchema": {"type": "object"}, "timeoutSeconds": 30,
    }}
    _publish(client, manifest)
    return manifest


def test_runtime_scope_comes_from_current_signed_session(client):
    manifest = publish_chain(client)
    target = {"method": "POST", "path": "/api/v1/industry-chain/research"}
    assert client.post(ENDPOINT, json=target).status_code == 401
    for user, workspace in [("alice", "first"), ("alice", "second"), ("bob", "first")]:
        headers = _session_headers(client, module_id=manifest["id"], user_id=user, workspace_id=workspace)
        response = client.post(ENDPOINT, headers={**headers, "X-User-Id": "forged", "X-Workspace-Id": "forged"}, json=target)
        assert response.status_code == 200, response.text
        assert response.json() == {"userId": user, "workspaceId": workspace}
        assert client.post(ENDPOINT, headers={**headers, "X-Newma-Desk-Instance-Id": "wrong"}, json=target).status_code == 403
    manifest["version"] = "1.0.1"
    _publish(client, manifest)
    assert client.post(ENDPOINT, headers=headers, json=target).status_code == 403
    client.app.state.mod_session_service._ttl_seconds = -1
    expired, _ = client.app.state.mod_session_service.issue(instance_id="instance-a", user_id="alice", workspace_id="first",
        module_id=manifest["id"], revision=2, actions=["analysis.industry-chain"], permissions=["analysis.read"])
    assert client.post(ENDPOINT, headers={**headers, "Authorization": "Bearer " + expired}, json=target).status_code == 401


def test_scope_does_not_grant_unrelated_analyses_or_arbitrary_paths(client):
    publish_chain(client)
    headers = _session_headers(client, module_id="instock-industry-chain")
    for path in ("/api/v1/analysis-history", "/api/v1/analysis-history/history-test", "/api/v1/analysis-snapshots/test:one"):
        assert client.post(ENDPOINT, headers=headers, json={"method": "GET", "path": path}).status_code == 200
    for method, path in [("POST", "/api/v1/research-books"), ("GET", "/api/v1/research-books"),
                         ("GET", "/api/v1/stock-research/dossiers"), ("DELETE", "/api/v1/analysis-history"),
                         ("GET", "https://other.invalid/api/v1/analysis-history")]:
        assert client.post(ENDPOINT, headers=headers, json={"method": method, "path": path}).status_code == 403
    _publish(client, _manifest("other-module"))
    other = _session_headers(client, module_id="other-module")
    assert client.post(ENDPOINT, headers=other, json={"method": "GET", "path": "/api/v1/analysis-history"}).status_code == 403


def test_action_forwards_validated_mod_session_not_identity_headers(client):
    publish_chain(client)
    headers = _session_headers(client, module_id="instock-industry-chain")
    fake = AsyncMock(return_value={"ok": True, "data": {}, "meta": {}})
    client.app.state.data_service_client.invoke = fake
    response = client.post("/api/mods/instock-industry-chain/actions/analysis.industry-chain", headers=headers, json={})
    assert response.status_code == 200, response.text
    assert fake.call_args.kwargs["mod_session"] == (headers["Authorization"].removeprefix("Bearer "), "instance-a")


def test_direct_service_route_preserves_session_and_rejects_incomplete_identity(client):
    publish_chain(client)
    headers = _session_headers(client, module_id="instock-industry-chain")
    fake = AsyncMock(return_value={"ok": True})
    client.app.state.data_service_client.invoke = fake
    path = "/api/data-services/instock-analysis/invoke/analysis.industry-chain"
    assert client.post(path, headers=headers, json={}).status_code == 200
    assert fake.call_args.kwargs["mod_session"] == (headers["Authorization"].removeprefix("Bearer "), "instance-a")
    assert client.post(path, headers={"Authorization": headers["Authorization"]}, json={}).status_code == 401
    assert client.post(path, headers={"X-Newma-Desk-Instance-Id": "instance-a"}, json={}).status_code == 401
