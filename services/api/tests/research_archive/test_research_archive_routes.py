from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def test_earnings_inputs_only_reads_current_workspace_revenue_and_references(tmp_path: Path):
    settings = Settings(runtime_dir=tmp_path, database_path=tmp_path / "desk.db", enable_domain_suites=False)
    with TestClient(create_app(settings)) as client:
        headers = {"X-User-Id": "archive-user", "X-Workspace-Id": "archive-workspace"}
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
        for other in ({**headers, "X-User-Id": "other"}, {**headers, "X-Workspace-Id": "other"}):
            assert client.get("/api/research-archive/earnings-inputs", headers=other).json()["workbooks"] == []
        assert client.get("/api/research-archive/earnings-inputs").status_code == 422


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
            headers={
                "X-User-Id": "archive-user",
                "X-Workspace-Id": "archive-workspace",
            },
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


def test_research_archive_isolated_by_user_and_workspace(tmp_path: Path):
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
            headers={
                "X-User-Id": "archive-user",
                "X-Workspace-Id": "archive-workspace",
            },
        )

        assert response.status_code == 200
        assert response.json()["entries"] == []
