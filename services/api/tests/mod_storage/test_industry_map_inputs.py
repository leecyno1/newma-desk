import copy
import json
import pytest

from tests.mod_storage.test_routes import client, _manifest, _publish, _session_headers
from tests.mod_storage.test_industry_maps import industry_manifest


def setup(client):
    _publish(client, industry_manifest())
    receiver = _manifest("instock-industry-chain")
    receiver["permissions"].append("analysis.read")
    _publish(client, receiver)
    source = _session_headers(client, module_id="industry-map")
    headers = _session_headers(client, module_id="instock-industry-chain")
    record = {"id": "edge-a", "target": json.dumps(["edge", "a", "b", "原关系", "flow"]),
              "title": "合成反证", "url": "https://example.com/", "locator": "p1", "excerpt": "仅为测试摘录",
              "judgment": "refutes", "recordedAt": "2026-10-19", "reviewRequired": {"targetLabel": "原关系", "reason": "结构变化"}}
    version = {"number": 1, "savedAt": "2026-10-19", "provenance": "synthetic", "spec": {
        "moduleId": "industry-map", "title": "测试图谱", "nodes": [{"id": key, "label": key} for key in ["a", "b", "c", "unrelated"]],
        "edges": [{"source": "a", "target": "b", "label": "新关系"}, {"source": "b", "target": "c"}]},
        "evidence": [record, {**record, "id": "unrelated", "target": "node:unrelated", "excerpt": "不应泄露无关片段"}]}
    book = {"schemaVersion": "newma-desk.industry-map.v1", "sectorKey": "hbm", "versions": [version]}
    storage = "/api/mods/industry-map/storage/industry-maps/hbm"
    assert client.put(storage, headers=source, json={"expectedRevision": 0, "value": book}).status_code == 200
    params = {"sector": "hbm", "node": "a", "version": 1, "revision": 1, "sourceUserId": "user-a", "sourceWorkspaceId": "workspace-a"}
    return source, headers, storage, book, params, receiver


endpoint = "/api/mods/instock-industry-chain/industry-map-inputs"


def test_selected_fragment_retains_counterevidence_and_never_writes(client):
    source, headers, storage, book, params, _ = setup(client)
    result = client.get(endpoint, headers=headers, params=params)
    assert result.status_code == 200, result.text
    data = result.json()
    assert [node["id"] for node in data["nodes"]] == ["a", "b"]
    assert len(data["edges"]) == len(data["evidence"]) == 1
    assert data["evidence"][0]["judgment"] == "refutes"
    assert data["evidence"][0]["reviewRequired"]["reason"] == "结构变化"
    assert data["claimVerified"] is False
    assert client.get(storage, headers=source).json()["value"] == book
    assert client.get("/api/artifacts?module_id=industry-map").json() == []


def test_signed_identity_cannot_be_overridden_by_query_or_headers(client):
    source, headers, _, _, params, _ = setup(client)
    assert client.get(endpoint, params=params).status_code == 401
    assert client.get(endpoint, headers=source, params=params).status_code == 403
    assert client.get(endpoint, headers={**headers, "X-Newma-Desk-Instance-Id": "wrong"}, params=params).status_code == 403
    for extra in ({"user_id": "user-b"}, {"workspace_id": "workspace-b"}):
        other = _session_headers(client, module_id="instock-industry-chain", **extra)
        assert client.get(endpoint, headers={**other, "X-User-Id": "user-a", "X-Workspace-Id": "workspace-a"}, params=params).status_code == 403
        own_params = {**params, "sourceUserId": extra.get("user_id", "user-a"), "sourceWorkspaceId": extra.get("workspace_id", "workspace-a")}
        assert client.get(endpoint, headers=other, params=own_params).status_code == 404


def test_changed_source_never_falls_back_to_latest_or_another_node(client):
    source, headers, storage, book, params, _ = setup(client)
    assert client.get(endpoint, headers=headers, params={**params, "node": "absent"}).status_code == 404
    assert client.get(endpoint, headers=headers, params={**params, "version": 2}).status_code == 404
    assert client.put(storage, headers=source, json={"expectedRevision": 1, "value": book}).status_code == 200
    assert client.get(endpoint, headers=headers, params=params).status_code == 409
    assert client.get(endpoint, headers=headers, params={**params, "revision": 2}).status_code == 200


def test_expired_and_old_receiver_sessions_fail_closed(client, monkeypatch):
    _, headers, _, _, params, receiver = setup(client)
    receiver["version"] = "1.0.1"
    _publish(client, receiver)
    assert client.get(endpoint, headers=headers, params=params).status_code == 403
    service = client.app.state.mod_session_service
    for permissions, expired, expected in [([], False, 403), (["analysis.read"], True, 401)]:
        if expired:
            monkeypatch.setattr(service, "_ttl_seconds", -1)
        token, _ = service.issue(instance_id="instance-a", user_id="user-a", workspace_id="workspace-a", module_id="instock-industry-chain", revision=2, actions=[], permissions=permissions)
        assert client.get(endpoint, headers={**headers, "Authorization": "Bearer " + token}, params=params).status_code == expected


def test_malformed_source_is_not_silently_accepted(client):
    source, headers, storage, book, params, _ = setup(client)
    bad = copy.deepcopy(book)
    bad["versions"][0]["evidence"][0]["judgment"] = "system-verified"
    assert client.put(storage, headers=source, json={"expectedRevision": 1, "value": bad}).status_code == 200
    assert client.get(endpoint, headers=headers, params={**params, "revision": 2}).status_code == 422


@pytest.mark.parametrize("consumer", ["instock-stock-research", "instock-research-book"])
def test_company_reads_exact_private_research_origin_without_replacing_historical_graph(client, consumer):
    source, headers, storage, book, params, receiver = setup(client)
    graph = client.get(endpoint, headers=headers, params=params).json()
    receiver["storage"]["namespaces"].append({"id": "research-origins", "scope": "user-workspace", "schemaVersion": 1, "quotaMb": 2, "maxItemKb": 512})
    _publish(client, receiver)
    headers = _session_headers(client, module_id="instock-industry-chain")
    company = _manifest(consumer)
    company["permissions"].append("analysis.read")
    _publish(client, company)
    company_headers = _session_headers(client, module_id=consumer)
    record = {"schemaVersion": "newma-desk.research-origin.v1", "snapshotId": "chain:test", "theme": "测试研究", "market": "CN", "asOf": "2026-08-08", "input": graph}
    key = "a" * 32
    saved = f"/api/mods/instock-industry-chain/storage/research-origins/{key}"
    assert client.put(saved, headers=headers, json={"expectedRevision": 0, "value": record}).status_code == 200
    assert client.put(saved, headers=headers, json={"expectedRevision": 0, "value": record}).status_code == 409
    path = f"/api/mods/{consumer}/research-origins/{key}"
    query = {key: record[key] for key in ["snapshotId", "theme", "market", "asOf"]}
    query.update(sourceUserId="user-a", sourceWorkspaceId="workspace-a")
    result = client.get(path, headers=company_headers, params=query)
    assert result.status_code == 200, result.text
    assert result.json()["record"] == record
    assert result.json()["record"]["input"]["evidence"][0]["judgment"] == "refutes"
    assert client.put(storage, headers=source, json={"expectedRevision": 1, "value": book}).status_code == 200
    assert client.get(path, headers=company_headers, params=query).json() == result.json()
    assert client.get(path, params=query).status_code == 401
    assert client.get(path, headers=headers, params=query).status_code == 403
    other_module = "instock-research-book" if consumer == "instock-stock-research" else "instock-stock-research"
    assert client.get(path.replace(consumer, other_module), headers=company_headers, params=query).status_code == 403
    for field in ["snapshotId", "theme", "market", "asOf"]:
        assert client.get(path, headers=company_headers, params={**query, field: "2026-08-09" if field == "asOf" else "wrong"}).status_code == 409
    other = _session_headers(client, module_id=consumer, workspace_id="other")
    assert client.get(path, headers=other, params=query).status_code == 403
    assert client.get(path, headers=other, params={**query, "sourceWorkspaceId": "other"}).status_code == 404
    company["version"] = "1.0.1"
    _publish(client, company)
    assert client.get(path, headers=company_headers, params=query).status_code == 403
