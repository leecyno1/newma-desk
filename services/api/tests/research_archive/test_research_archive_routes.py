from pathlib import Path
import pytest

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from tests.mod_storage.test_routes import _manifest, _publish, _session_headers


def _archive_headers(client):
    _publish(client, _manifest("research-memo"))
    return _session_headers(client, module_id="research-memo", user_id="archive-user", workspace_id="archive-workspace")


def _input_headers(client, module_id):
    manifest = _manifest(module_id)
    if module_id == 'instock-industry-chain':
        manifest['permissions'].append('analysis.read')
    _publish(client, manifest)
    return _session_headers(client, module_id=module_id, user_id='archive-user', workspace_id='archive-workspace')


def test_earnings_inputs_only_reads_current_workspace_revenue_and_references(tmp_path: Path):
    settings = Settings(runtime_dir=tmp_path, database_path=tmp_path / "desk.db", enable_domain_suites=False)
    with TestClient(create_app(settings)) as client:
        headers = _input_headers(client, "valuation-workbench")
        assert client.get("/api/research-archive/earnings-inputs", headers=headers).json() == {"revision": 0, "workbooks": []}
        _put_document(client, module_id="earnings-workbench", namespace="earnings-workbench", key="workbooks", value={
            "workbooks": [{"id": "annual-2024", "security": {"symbol": "600519", "currency": "CNY"},
                "fiscalPeriod": {"periodEnd": "2024-12-31", "basis": "annual"}, "mode": "reported",
                "updatedAt": "2026-09-20", "headline": "Private commentary",
                "metrics": [{"id": "revenue", "reported": 1708.9915227634, "unit": "亿元", "sourceIds": ["revenue-pdf"]},
                            {"id": "profit", "reported": 862}],
                "operatingMetrics": [{"id": "capital-cash-funds", "reported": 59295, "sourceIds": ["cash-pdf"]},
                                     {"id": "other", "reported": 1, "sourceIds": ["other-pdf"]}],
                "sourceMaterials": [{"id": "revenue-pdf", "excerpt": {"metricId": "revenue", "pdfPage": 5}, "discussion": {"text": "Not needed"}},
                                    {"id": "cash-pdf", "excerpt": {"metricId": "capital-cash-funds", "pdfPage": 58}},
                                    {"id": "cash-note", "capitalNote": {"text": "不属于现金等价物的货币资金", "pdfPage": 117}, "discussion": {"text": "Not needed"}},
                                    {"id": "profit-pdf", "excerpt": {"text": "Not needed"}}]}]})
        payload = client.get("/api/research-archive/earnings-inputs", headers=headers).json()
        assert payload["revision"] == 1
        row = payload["workbooks"][0]
        assert len(row["metrics"]) == len(row["operatingMetrics"]) == 1
        assert len(row["sourceMaterials"]) == 3
        assert row["sourceMaterials"][2]["capitalNote"]["pdfPage"] == 117
        assert "discussion" not in row["sourceMaterials"][2]
        assert row["operatingMetrics"][0]["id"] == "capital-cash-funds"
        assert row["metrics"][0]["reported"] == 1708.9915227634
        assert row["sourceMaterials"][0]["excerpt"]["pdfPage"] == 5
        assert "discussion" not in row["sourceMaterials"][0]
        assert "headline" not in row
        for other in (_session_headers(client, module_id='valuation-workbench', user_id='other', workspace_id='archive-workspace'),
                      _session_headers(client, module_id='valuation-workbench', user_id='archive-user', workspace_id='other')):
            assert client.get("/api/research-archive/earnings-inputs", headers=other).json()["workbooks"] == []
        spoofed = client.get('/api/research-archive/earnings-inputs', headers={**headers, 'X-User-Id':'other', 'X-Workspace-Id':'other'})
        assert spoofed.json() == payload
        assert spoofed.headers['Cache-Control'] == 'private, no-store'
        assert client.get("/api/research-archive/earnings-inputs").status_code == 401


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
    ('earnings-inputs', 'valuation-workbench', 'storage.read'),
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


def test_research_archive_derives_reference_only_index(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "desk.db",
        enable_domain_suites=False,
    )
    with TestClient(create_app(settings)) as client:
        _put_document(
            client,
            module_id="research-notes",
            namespace="research-notes",
            key="records",
            value={
                "schemaVersion": "newma-desk.research-records.v1",
                "updatedAt": "2026-08-05T01:00:00Z",
                "records": [
                    {
                        "id": "note:1",
                        "kind": "问AI",
                        "title": "光模块需求复盘",
                        "content": "这段正文不应进入统一索引。",
                        "ts": 1785891600000,
                    }
                ],
            },
        )
        _put_document(
            client,
            module_id="thesis-tracker",
            namespace="thesis-tracker",
            key="portfolio",
            value={
                "schemaVersion": "newma-desk.investment-thesis.v1",
                "updatedAt": "2026-08-05T02:00:00Z",
                "theses": [
                    {
                        "id": "thesis:1",
                        "title": "中际旭创产品迭代逻辑",
                        "status": "active",
                        "conviction": "medium",
                        "security": {
                            "market": "CN",
                            "symbol": "300308",
                            "name": "中际旭创",
                        },
                        "statement": "完整投资逻辑正文不应进入统一索引。",
                        "nextReviewAt": "2026-09-01",
                        "updatedAt": "2026-08-05T02:00:00Z",
                    }
                ],
            },
        )
        _put_document(
            client,
            module_id="research-memo",
            namespace="research-memo",
            key="memos",
            value={
                "schemaVersion": "newma-desk.research-memo.v1",
                "updatedAt": "2026-08-05T03:00:00Z",
                "memos": [
                    {
                        "id": "memo:1",
                        "title": "光模块研究备忘录",
                        "status": "current",
                        "security": {
                            "market": "CN",
                            "symbol": "300308",
                            "name": "中际旭创",
                        },
                        "boundary": {"asOf": "2026-08-05"},
                        "executiveView": {
                            "bias": "neutral",
                            "conviction": "medium",
                            "conclusion": "完整结论不应进入统一索引。",
                        },
                        "updatedAt": "2026-08-05T03:00:00Z",
                    }
                ],
            },
        )

        response = client.get(
            "/api/research-archive",
            headers=_archive_headers(client),
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["schemaVersion"] == "newma-desk.research-archive.v1"
        assert [entry["kind"] for entry in payload["entries"]] == [
            "research-memo",
            "thesis",
            "research-record",
        ]
        assert payload["entries"][0] == {
            "id": "archive:research-memo:memo:1",
            "kind": "research-memo",
            "sourceModId": "research-memo",
            "artifactId": "memo:1",
            "title": "光模块研究备忘录",
            "status": "active",
            "security": {
                "market": "CN",
                "symbol": "300308",
                "name": "中际旭创",
            },
            "asOf": "2026-08-05",
            "updatedAt": "2026-08-05T03:00:00Z",
            "tags": ["current", "neutral", "medium"],
            "sourceRevision": 1,
        }
        serialized = response.text
        assert "这段正文不应进入统一索引" not in serialized
        assert "完整投资逻辑正文不应进入统一索引" not in serialized
        assert "完整结论不应进入统一索引" not in serialized


@pytest.mark.parametrize('reader', ['research-memo', 'idea-funnel'])
def test_research_archive_isolated_by_user_and_workspace(tmp_path: Path, reader):
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "desk.db",
        enable_domain_suites=False,
    )
    with TestClient(create_app(settings)) as client:
        _put_document(
            client,
            module_id="research-notes",
            namespace="research-notes",
            key="records",
            user_id="other-user",
            workspace_id="other-workspace",
            value={
                "records": [
                    {
                        "id": "note:private",
                        "kind": "复盘",
                        "title": "其他工作区记录",
                        "content": "private",
                        "ts": 1785891600000,
                    }
                ]
            },
        )

        response = client.get(
            "/api/research-archive",
            headers={**_input_headers(client, reader), "X-User-Id": "other-user", "X-Workspace-Id": "other-workspace"},
        )

        assert response.status_code == 200
        assert response.json()["entries"] == []


@pytest.mark.parametrize('reader', ['research-memo', 'idea-funnel'])
def test_archive_requires_current_authorized_session(tmp_path: Path, reader):
    settings = Settings(runtime_dir=tmp_path, database_path=tmp_path / "desk.db", enable_domain_suites=False)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/research-archive", headers={"X-User-Id": "archive-user", "X-Workspace-Id": "archive-workspace"}).status_code == 401
        headers = _input_headers(client, reader)
        assert client.get("/api/research-archive", headers={**headers, "X-Newma-Desk-Instance-Id": "wrong"}).status_code == 403
        assert client.get("/api/research-archive", headers=headers).status_code == 200
        _publish(client, _manifest("research-notes"))
        assert client.get("/api/research-archive", headers=_session_headers(client)).status_code == 403
        library = _manifest("research-library")
        library["permissions"].append("investment.read")
        _publish(client, library)
        assert client.get("/api/research-archive", headers=_session_headers(client, module_id="research-library")).status_code == 200
        changed = _manifest(reader)
        changed["version"] = "1.1.0"
        _publish(client, changed)
        assert client.get("/api/research-archive", headers=headers).status_code == 403


def test_archive_reports_unreadable_source_instead_of_missing_reference(tmp_path: Path, monkeypatch):
    from vibe_visualization_api.mod_storage.store import ModStorageCorruptError
    settings = Settings(runtime_dir=tmp_path, database_path=tmp_path / "desk.db", enable_domain_suites=False)
    with TestClient(create_app(settings)) as client:
        headers = _archive_headers(client)
        _put_document(client, module_id="thesis-tracker", namespace="thesis-tracker", key="portfolio", value={"theses": [{
            "id": "t1", "title": "研究逻辑", "status": "active", "nextReviewAt": "2028-01-01", "updatedAt": "2026-10-01T00:00:00Z",
        }]})
        original = client.app.state.mod_storage_store.get
        def damaged(**kwargs):
            if kwargs["module_id"] == "valuation-workbench":
                raise ModStorageCorruptError("private details")
            return original(**kwargs)
        monkeypatch.setattr(client.app.state.mod_storage_store, "get", damaged)
        response = client.get("/api/research-archive", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["unavailableSources"] == ["valuation-workbench"]
        assert payload["truncated"] is False
        assert len(payload["entries"]) == 1
        assert payload["entries"][0].get("asOf") is None  # Review due date is not data as-of.
        assert "private details" not in response.text
