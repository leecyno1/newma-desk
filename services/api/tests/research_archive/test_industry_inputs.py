from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient
from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from tests.mod_storage.test_routes import _manifest, _publish, _session_headers


def _archive_headers(client):
    _publish(client, _manifest("research-memo"))
    return _session_headers(client, module_id="research-memo", user_id="archive-user", workspace_id="archive-workspace")


def test_real_industry_manifest_supports_tracking_and_private_inputs(tmp_path):
    root = Path(__file__).resolve().parents[4]
    descriptor = json.loads((root / 'mods/industry-prosperity/mod.json').read_text())
    manifest = {**descriptor['manifest'], **{key: descriptor[key] for key in ('id', 'name', 'version')},
                'entry': {'type': 'external', 'url': 'https://assets.example/mod-runtime/industry-research/'}}
    settings = Settings(runtime_dir=tmp_path, database_path=tmp_path / 'desk.db', enable_domain_suites=False)
    with TestClient(create_app(settings)) as client:
        _publish(client, manifest)
        headers = _session_headers(client, module_id=descriptor['id'])
        evidence = client.get('/api/research-archive/industry-inputs', headers=headers)
        assert evidence.status_code == 200
        assert evidence.json() == {'revision': 0, 'workbooks': []}
        assert evidence.headers['cache-control'] == 'private, no-store'
        for key in ('records', 'company-links'):
            path = f'/api/mods/industry-prosperity/storage/industry-tracking/{key}'
            value = {'version': 1, 'entries': [], 'note': 'isolated acceptance only'}
            assert client.get(path, headers=headers).status_code == 404
            result = client.put(path, headers=headers, json={'expectedRevision': 0, 'value': value})
            assert result.status_code == 200, result.text
            assert client.get(path, headers=headers).json()['value'] == value
            assert client.put(path, headers=headers, json={'expectedRevision': 0, 'value': value}).status_code == 409
            other = _session_headers(client, module_id=descriptor['id'], workspace_id='other')
            assert client.get(path, headers=other).status_code == 404


def _input_headers(client, module_id):
    manifest = _manifest(module_id)
    if module_id == 'instock-industry-chain':
        manifest['permissions'].append('analysis.read')
    _publish(client, manifest)
    return _session_headers(client, module_id=module_id, user_id='archive-user', workspace_id='archive-workspace')


def _put_document(
    client: TestClient,
    *,
    module_id: str,
    namespace: str,
    key: str,
    value: dict,
    user_id: str = "archive-user",
    workspace_id: str = "archive-workspace",
):
    return client.app.state.mod_storage_store.put(
        user_id=user_id,
        workspace_id=workspace_id,
        module_id=module_id,
        namespace=namespace,
        key=key,
        schema_version=1,
        expected_revision=0,
        value=value,
        quota_bytes=8 * 1024 * 1024,
        max_item_bytes=2 * 1024 * 1024,
    )


def test_industry_inputs_preserve_selected_metrics_and_isolate_workspace(tmp_path: Path):
    settings = Settings(runtime_dir=tmp_path, database_path=tmp_path / "desk.db", enable_domain_suites=False)
    with TestClient(create_app(settings)) as client:
        headers = _input_headers(client, "industry-prosperity")
        assert client.get("/api/research-archive/industry-inputs").status_code == 401
        assert client.get("/api/research-archive/industry-inputs", headers=headers).json() == {"revision": 0, "workbooks": []}
        _put_document(client, module_id="earnings-workbench", namespace="earnings-workbench", key="workbooks", value={"workbooks": [{
            "id": "test", "security": {"name": "测试公司", "symbol": "000001", "currency": "CNY", "market": "CN"},
            "fiscalPeriod": {"periodEnd": "2025-12-31", "basis": "annual"}, "mode": "reported", "headline": "private",
            "metrics": [{"id": "revenue", "reported": 100, "sourceIds": ["revenue-source"]}, {"id": "eps", "reported": 2}],
            "operatingMetrics": [{"id": "operating-cash-flow", "reported": 20, "sourceIds": ["cash-source"]}, {"id": "other", "reported": 3},
                                 {"id": "capital-inventory", "reported": 10, "reportedBasis": "instant", "sourceIds": ["balance-source"]},
                                 {"id": "capital-accounts-receivable", "reported": None, "reportedBasis": "instant", "sourceIds": []}],
            "sourceMaterials": [{"id": "revenue-source", "discussion": {"text": "private"}, "capitalNote": {"text": "private"}},
                                {"id": "cash-source", "excerpt": {"metricId": "operating-cash-flow", "pdfPage": 6}}, {"id": "unrelated"},
                                {"id": "balance-source", "basis": "instant", "importedReport": {"scope": "consolidated"}, "excerpt": {"pdfPage": 59}},
                                {"id": "business-source", "basis": "annual", "businessRevenue": {"dimension": "product", "rows": [{"label": "测试产品", "value": 80}]}, "discussion": {"text": "private"}}]}]})
        result = client.get("/api/research-archive/industry-inputs", headers=headers).json()
        assert result["revision"] == 1
        row = result["workbooks"][0]
        assert [metric["id"] for metric in row["metrics"]] == ["revenue", "operating-cash-flow", "capital-inventory", "capital-accounts-receivable"]
        assert row["metrics"][-1]["reported"] is None
        assert row["metrics"][-2]["reportedBasis"] == "instant"
        assert len(row["sourceMaterials"]) == 4
        assert row["sourceMaterials"][3]["businessRevenue"]["dimension"] == "product"
        assert "discussion" not in row["sourceMaterials"][3]
        assert row["sourceMaterials"][2]["basis"] == "instant"
        assert row["sourceMaterials"][2]["importedReport"]["scope"] == "consolidated"
        assert row["sourceMaterials"][1]["excerpt"]["pdfPage"] == 6
        assert "headline" not in row and "discussion" not in row["sourceMaterials"][0] and "capitalNote" not in row["sourceMaterials"][0]
        for other in (_session_headers(client, module_id='industry-prosperity', user_id='other', workspace_id='archive-workspace'),
                      _session_headers(client, module_id='industry-prosperity', user_id='archive-user', workspace_id='other')):
            assert client.get("/api/research-archive/industry-inputs", headers=other).json()["workbooks"] == []
        assert client.get('/api/research-archive/industry-inputs', headers={**headers, 'X-User-Id':'other', 'X-Workspace-Id':'other'}).json() == result
        assert client.get('/api/research-archive/industry-inputs', headers=_input_headers(client, 'instock-industry-chain')).json() == result
        # Read-only projection must not update the source revision.
        assert client.get("/api/research-archive/industry-inputs", headers=headers).json()["revision"] == 1


@pytest.mark.parametrize('endpoint,module_id,permission', [
    ('industry-inputs', 'industry-prosperity', 'storage.read'),
    ('industry-inputs', 'instock-industry-chain', 'analysis.read'),
])
def test_input_session_permissions_instance_revision_and_read_failures(tmp_path, monkeypatch, endpoint, module_id, permission):
    from vibe_visualization_api.mod_storage.store import ModStorageCorruptError
    settings = Settings(runtime_dir=tmp_path, database_path=tmp_path / 'desk.db', enable_domain_suites=False)
    with TestClient(create_app(settings)) as client:
        path = f'/api/research-archive/{endpoint}'
        assert client.get(path, headers={'X-User-Id':'archive-user','X-Workspace-Id':'archive-workspace'}).status_code == 401
        headers = _input_headers(client, module_id)
        assert client.get(path, headers={**headers, 'X-Newma-Desk-Instance-Id':'wrong'}).status_code == 403
        assert client.get(path, headers=_archive_headers(client)).status_code == 403
        # A valid token with the right module but without the required grant is rejected.
        token, _ = client.app.state.mod_session_service.issue(instance_id='frame', user_id='archive-user',
            workspace_id='archive-workspace', module_id=module_id, revision=1, permissions=[], actions=[])
        assert client.get(path, headers={'Authorization':f'Bearer {token}', 'X-Newma-Desk-Instance-Id':'frame'}).status_code == 403
        def broken(**_kwargs):
            raise ModStorageCorruptError('private file details')
        method = 'earnings_inputs' if endpoint == 'earnings-inputs' else 'industry_inputs'
        monkeypatch.setattr(client.app.state.research_archive_service, method, broken)
        response = client.get(path, headers=headers)
        assert response.status_code == 503
        assert 'private file details' not in response.text
        changed = _manifest(module_id)
        changed['permissions'].append(permission)
        changed['permissions'] = list(set(changed['permissions']))
        changed['version'] = '1.1.0'
        _publish(client, changed)
        assert client.get(path, headers=headers).status_code == 403
