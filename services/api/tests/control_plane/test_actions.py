import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.agent_gateway.fakes import FakeAgentAdapter
from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.actions import (
    TradeConfirmationService,
    payload_hash,
)
from vibe_visualization_api.data_services.models import (
    DataServiceDescriptor,
    ServiceCapability,
)
from vibe_visualization_api.main import create_app
from vibe_visualization_api.snapshots.store import SnapshotStore


MANIFEST = {
    "schemaVersion": "1.0",
    "id": "market-daily",
    "name": "每日股票行情",
    "version": "0.1.0",
    "category": "market",
    "entry": {"type": "external", "url": "https://example.com/market"},
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "agentCapabilities": ["market.explain"],
    "events": {"emits": [], "accepts": []},
}


class FakeDataClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def invoke(
        self,
        service: DataServiceDescriptor,
        capability_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, object]:
        self.calls.append((service.id, capability_id, input_data))
        return {"breadth": 0.63}


class FakeRefreshService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def refresh_module(self, module_id: str) -> dict[str, object]:
        self.calls.append(module_id)
        return {
            "id": "snapshot-1",
            "moduleId": module_id,
            "data": {"asOf": "2026-07-20T15:00:00+08:00"},
        }


@pytest.fixture
def fake_adapter() -> FakeAgentAdapter:
    return FakeAgentAdapter()


@pytest.fixture
def fake_data_client() -> FakeDataClient:
    return FakeDataClient()


@pytest.fixture
def fake_refresh_service() -> FakeRefreshService:
    return FakeRefreshService()


@pytest.fixture
def client(
    tmp_path: Path,
    fake_adapter: FakeAgentAdapter,
    fake_data_client: FakeDataClient,
    fake_refresh_service: FakeRefreshService,
) -> Iterator[TestClient]:
    service = DataServiceDescriptor(
        id="market-data",
        base_url="http://127.0.0.1:9000/api",
        transport="rest",
        allowed_hosts=["127.0.0.1"],
        capabilities={
            "market.overview": ServiceCapability(
                method="POST",
                path="/overview",
                input_schema="MarketOverviewInput",
                output_schema="MarketOverviewOutput",
                permission="market.read",
            )
        },
    )
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "actions.db",
        agent_default_adapter="fake",
        trade_confirmation_secret="test-confirmation-secret",
    )
    application = create_app(
        settings,
        agent_adapters=[fake_adapter],
        data_services=[service],
        data_service_client=fake_data_client,
        scheduler_service=fake_refresh_service,
    )
    with TestClient(application) as test_client:
        yield test_client


def _publish(client: TestClient, manifest: dict[str, object] = MANIFEST) -> int:
    draft = client.post("/api/modules/drafts", json=manifest).json()
    response = client.post(
        f"/api/modules/{manifest['id']}/revisions/{draft['revision']}/publish"
    )
    assert response.status_code == 200
    return draft["revision"]


def _audit_details(database_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT detail_json FROM audit_events "
            "WHERE event_type = 'module_action' ORDER BY id"
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def test_published_module_can_call_declared_agent_capability(
    client: TestClient,
    tmp_path: Path,
    fake_adapter: FakeAgentAdapter,
) -> None:
    _publish(client)
    SnapshotStore(tmp_path, tmp_path / "actions.db").write_success(
        "market-daily",
        {
            "asOf": "2026-07-20T15:00:00+08:00",
            "breadth": {"up": 3000, "down": 1800, "flat": 100},
            "indices": [],
            "globalIndices": [],
            "leaders": [],
        },
    )

    response = client.post(
        "/api/modules/market-daily/actions/market.explain",
        headers={"X-User-Id": "alice"},
        json={"prompt": "解释市场异动"},
    )

    assert response.status_code == 202
    assert response.json()["request"]["moduleId"] == "market-daily"
    assert response.json()["request"]["capability"] == "market.explain"
    deadline = time.monotonic() + 1
    while not fake_adapter.requests and time.monotonic() < deadline:
        time.sleep(0.01)
    assert fake_adapter.requests[0].input == {}
    assert "解释市场异动" in fake_adapter.requests[0].prompt
    assert "breadth" in fake_adapter.requests[0].prompt
    audit = _audit_details(tmp_path / "actions.db")[-1]
    assert audit["decision"] == "allowed"
    assert audit["user_id"] == "alice"
    assert audit["task_id"].startswith("task-")


def test_published_module_can_call_declared_data_capability(
    client: TestClient,
    fake_data_client: FakeDataClient,
) -> None:
    _publish(client)

    response = client.post(
        "/api/modules/market-daily/actions/market.overview",
        json={"date": "2026-07-20"},
    )

    assert response.status_code == 200
    assert response.json() == {"breadth": 0.63}
    assert fake_data_client.calls == [
        ("market-data", "market.overview", {"date": "2026-07-20"})
    ]


def test_market_refresh_runs_locally_instead_of_creating_an_agent_task(
    client: TestClient,
    tmp_path: Path,
    fake_adapter: FakeAgentAdapter,
    fake_refresh_service: FakeRefreshService,
) -> None:
    _publish(
        client,
        {
            **MANIFEST,
            "agentCapabilities": ["market.explain", "market.refresh"],
        },
    )

    response = client.post(
        "/api/modules/market-daily/actions/market.refresh",
        headers={"X-User-Id": "alice"},
        json={},
    )

    assert response.status_code == 200
    assert response.json()["data"]["asOf"] == "2026-07-20T15:00:00+08:00"
    assert fake_refresh_service.calls == ["market-daily"]
    assert fake_adapter.requests == []
    audit = _audit_details(tmp_path / "actions.db")[-1]
    assert audit["decision"] == "allowed"
    assert audit["snapshot_id"] == "snapshot-1"


def test_undeclared_capability_returns_forbidden_and_is_audited(
    client: TestClient,
    tmp_path: Path,
) -> None:
    _publish(client)

    response = client.post(
        "/api/modules/market-daily/actions/market.delete",
        json={},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "module action is not declared"}
    assert _audit_details(tmp_path / "actions.db")[-1]["decision"] == "denied"


def test_disabled_module_returns_conflict(client: TestClient) -> None:
    _publish(client)
    client.post("/api/modules/market-daily/disable")

    response = client.post(
        "/api/modules/market-daily/actions/market.explain",
        json={},
    )

    assert response.status_code == 409


def test_trade_execute_requires_matching_confirmation_and_remains_disabled(
    client: TestClient,
) -> None:
    trade_manifest = {
        **MANIFEST,
        "permissions": ["market.read", "trade.execute"],
    }
    _publish(client, trade_manifest)
    action_url = "/api/modules/market-daily/actions/trade.execute"
    trade_input = {"symbol": "600519", "quantity": 100}

    missing = client.post(action_url, headers={"X-User-Id": "alice"}, json=trade_input)
    confirmation = TradeConfirmationService("test-confirmation-secret")
    wrong_payload_token = confirmation.issue(
        user_id="alice",
        module_id="market-daily",
        action_id="trade.execute",
        payload_hash=payload_hash({"symbol": "600519", "quantity": 200}),
    )
    wrong = client.post(
        action_url,
        headers={
            "X-User-Id": "alice",
            "X-Confirmation-Token": wrong_payload_token,
        },
        json=trade_input,
    )
    valid_token = confirmation.issue(
        user_id="alice",
        module_id="market-daily",
        action_id="trade.execute",
        payload_hash=payload_hash(trade_input),
    )
    valid = client.post(
        action_url,
        headers={
            "X-User-Id": "alice",
            "X-Confirmation-Token": valid_token,
        },
        json=trade_input,
    )

    assert missing.status_code == 428
    assert wrong.status_code == 428
    assert valid.status_code == 501
    assert valid.json() == {"detail": "real trading is disabled in the MVP"}
