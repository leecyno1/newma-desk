import time
from pathlib import Path

from fastapi.testclient import TestClient

from orchestra_app import api
from orchestra_app.security import SecretVault
from orchestra_app.service import CommitteeService
from orchestra_app.storage import SQLiteStore


def _wait_for_run(client: TestClient, run_id: str) -> dict:
    deadline = time.time() + 20
    while time.time() < deadline:
        payload = client.get(f"/api/runs/{run_id}").json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def _wait_for_intervention(client: TestClient, run_id: str, agent_id: str) -> dict:
    deadline = time.time() + 10
    while time.time() < deadline:
        payload = client.get(f"/api/runs/{run_id}").json()
        runtime = payload["agents"][agent_id]
        if runtime["phase"] == "intervention" and runtime["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError("intervention did not finish")


def test_persistent_resources_revision_comparison_and_exports(tmp_path: Path, monkeypatch) -> None:
    service = CommitteeService(
        SQLiteStore(tmp_path / "api.db"),
        SecretVault(tmp_path / "secret.key"),
    )
    monkeypatch.setattr(api, "committee_service", service)

    with TestClient(api.app) as client:
        overview = client.get("/api/system/overview")
        assert overview.status_code == 200
        assert overview.json()["persistence"] == "sqlite"
        assert overview.json()["queue_backend"] == "sqlite-durable"

        created_user = client.post(
            "/api/users",
            json={"name": "隔离研究员", "role": "researcher"},
        )
        assert created_user.status_code == 201
        isolated_user = created_user.json()["user"]
        api_token = created_user.json()["api_token"]
        assert client.get(
            "/api/users/me",
            headers={"X-Orchestra-User": isolated_user["id"]},
        ).status_code == 401
        assert client.get(
            "/api/users/me",
            headers={
                "X-Orchestra-User": isolated_user["id"],
                "Authorization": f"Bearer {api_token}",
            },
        ).status_code == 200

        session = client.post(
            "/api/auth/session",
            json={"user_id": isolated_user["id"], "api_token": api_token},
        )
        assert session.status_code == 201
        assert session.json()["user"]["id"] == isolated_user["id"]
        assert "orchestra_session=" in session.headers["set-cookie"]
        assert "HttpOnly" in session.headers["set-cookie"]
        assert client.get("/api/users/me").json()["id"] == isolated_user["id"]
        assert client.get("/api/runs/missing/events").status_code == 404

        isolated_portfolio = client.post(
            "/api/portfolios",
            json={"name": "隔离组合", "description": "会话账本", "base_currency": "CNY"},
        )
        assert isolated_portfolio.status_code == 201
        transaction = client.post(
            f"/api/portfolios/{isolated_portfolio.json()['id']}/transactions",
            json={"transaction_type": "cash_in", "amount": "500000", "currency": "CNY"},
        )
        assert transaction.status_code == 201
        detail = client.get(f"/api/portfolios/{isolated_portfolio.json()['id']}")
        assert detail.status_code == 200
        assert detail.json()["summary"]["net_asset_value"] == "500000"

        logout = client.delete("/api/auth/session")
        assert logout.status_code == 204
        assert client.get("/api/users/me").json()["id"] == "local-user"

        portfolio = client.post(
            "/api/portfolios",
            json={"name": "稳健组合", "description": "低回撤", "base_currency": "CNY"},
        )
        assert portfolio.status_code == 201

        secret = client.post(
            "/api/secrets",
            json={"provider": "tushare", "label": "测试密钥", "value": "token-123456789"},
        )
        assert secret.status_code == 201
        assert "value" not in secret.json()

        created = client.post(
            "/api/runs",
            json={
                "topic": "API 持久化测试",
                "mode": "demo",
                "portfolio_id": portfolio.json()["id"],
            },
        )
        assert created.status_code == 202
        first = _wait_for_run(client, created.json()["run_id"])
        assert first["status"] == "completed"

        agent_id = next(iter(first["agents"]))
        intervention = client.post(
            f"/api/runs/{first['id']}/agents/{agent_id}/interventions",
            json={"action": "follow_up", "instruction": "原结论最重要的反证是什么？"},
        )
        assert intervention.status_code == 202
        intervened = _wait_for_intervention(client, first["id"], agent_id)
        assert intervened["agents"][agent_id]["intervention_action"] == "follow_up"

        revision = client.post(
            f"/api/runs/{first['id']}/revisions",
            json={"note": "加入新证据后复议"},
        )
        assert revision.status_code == 202
        second = _wait_for_run(client, revision.json()["run_id"])
        assert second["revision"] == 2
        assert second["parent_run_id"] == first["id"]

        comparison = client.post(
            "/api/run-comparisons",
            json={"run_ids": [first["id"], second["id"]]},
        )
        assert comparison.status_code == 200
        assert len(comparison.json()["comparisons"]) == 1

        artifacts = client.get(f"/api/runs/{first['id']}/artifacts")
        assert artifacts.status_code == 200
        assert len(artifacts.json()) >= 21

        pdf = client.get(f"/api/runs/{first['id']}/exports/pdf")
        word = client.get(f"/api/runs/{first['id']}/exports/docx")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert word.status_code == 200 and word.content.startswith(b"PK")
